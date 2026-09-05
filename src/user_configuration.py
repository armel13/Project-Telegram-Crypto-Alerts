import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from functools import wraps
from threading import RLock

from .config import *
from .config import PLANS
from .mongo import MongoDBConnection

_USER_DATA_LOCKS: dict[str, RLock] = {}
_USER_DATA_LOCKS_GUARD = RLock()


def _get_user_data_lock(user_id: str) -> RLock:
    """Return the process-wide lock shared by all config objects for a user."""
    with _USER_DATA_LOCKS_GUARD:
        return _USER_DATA_LOCKS.setdefault(str(user_id), RLock())


@contextmanager
def user_data_lock(user_id: str):
    """Prevent Telegram and alert-worker threads mutating one user concurrently."""
    with _get_user_data_lock(user_id):
        yield


def synchronized_user_data(func):
    """Serialize a worker method whose first argument after self is a user ID."""

    @wraps(func)
    def wrapper(self, tg_user_id: str, *args, **kwargs):
        with user_data_lock(tg_user_id):
            return func(self, tg_user_id, *args, **kwargs)

    return wrapper


def synchronized_message_user_data(func):
    """Serialize a Telegram handler that mutates the caller's stored data."""

    @wraps(func)
    def wrapper(message, *args, **kwargs):
        with user_data_lock(str(message.from_user.id)):
            return func(message, *args, **kwargs)

    return wrapper


def _atomic_write_json(path: str, data: dict) -> None:
    """Durably replace a JSON file without exposing readers to partial content."""
    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(prefix=".tmp-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as outfile:
            json.dump(data, outfile, indent=2)
            outfile.flush()
            os.fsync(outfile.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


# Activate mongo DB connection if needed
if USE_MONGO_DB:
    db_connection = MongoDBConnection()


class LocalUserConfiguration:
    """Simplifies interaction with the json database system"""

    def __init__(self, tg_user_id: str):
        """
        :param tg_user_id: The Telegram user ID of the bot user to locate their configuration
        """
        self.user_id = tg_user_id
        self.user_config_root = join(WHITELIST_ROOT, f"{self.user_id}")
        self.config_path = join(WHITELIST_ROOT, f"{self.user_id}", "config.json")
        self.alerts_path = join(WHITELIST_ROOT, f"{self.user_id}", "alerts.json")

        # Utility Paths:
        self.default_alerts_path = join(RESOURCES_ROOT, "default_alerts.json")
        self.default_config_path = join(RESOURCES_ROOT, "default_config.json")

    def whitelist_user(self, is_admin: bool = False, username: str = None):
        """Add necessary files and directories to database for TG user ID"""
        with user_data_lock(self.user_id):
            if self.user_id in get_whitelist():
                return

            mkdir(self.user_config_root)

            try:
                from datetime import datetime, timezone

                with open(self.default_config_path, "r", encoding="utf-8") as _in:
                    default_config = json.load(_in)

                default_config["channels"].append(self.user_id)
                if is_admin:
                    default_config["is_admin"] = True

                now = datetime.now(timezone.utc).isoformat()
                default_config["telegram_id"] = self.user_id
                if username:
                    default_config["username"] = username
                default_config["plan"] = "free"
                default_config["max_alerts"] = PLANS.get("free", 3)
                default_config["created_at"] = now
                default_config["updated_at"] = now
                _atomic_write_json(self.config_path, default_config)

                with open(self.default_alerts_path, "r", encoding="utf-8") as _in:
                    _atomic_write_json(self.alerts_path, json.load(_in))
            except Exception:
                shutil.rmtree(self.user_config_root, ignore_errors=True)
                raise

    def blacklist_user(self):
        """Remove TG user configuration from database"""
        # Removes user configuration recursively
        with user_data_lock(self.user_id):
            if exists(self.user_config_root):
                shutil.rmtree(self.user_config_root)

    def load_alerts(self) -> dict:
        """Load the database contents and return it in JSON format"""
        with user_data_lock(self.user_id):
            with open(self.alerts_path, "r", encoding="utf-8") as infile:
                return json.load(infile)

    def update_alerts(self, data: dict) -> None:
        with user_data_lock(self.user_id):
            _atomic_write_json(self.alerts_path, data)

    def load_config(self) -> dict:
        with user_data_lock(self.user_id):
            with open(self.config_path, "r", encoding="utf-8") as infile:
                return json.load(infile)

    def update_config(self, data: dict) -> None:
        with user_data_lock(self.user_id):
            _atomic_write_json(self.config_path, data)

    def admin_status(self, new_value: bool = None) -> bool:
        config = self.load_config()
        if new_value is not None:
            config["is_admin"] = new_value
            self.update_config(config)
        return config.get("is_admin", False)

    def get_plan(self) -> str:
        config = self.load_config()
        return config.get("plan", "free")

    def set_plan(self, plan: str) -> None:
        config = self.load_config()
        from datetime import datetime

        config["plan"] = plan
        config["max_alerts"] = PLANS.get(plan, 3)
        config["updated_at"] = datetime.utcnow().isoformat()
        self.update_config(config)

    def get_channels(self) -> list[str]:
        return self.load_config().get("channels", [])

    def add_channels(self, channels: list[str]) -> None:
        config = self.load_config()
        for channel in channels:
            if channel not in config["channels"]:
                config["channels"].append(channel)
        self.update_config(config)

    def remove_channels(self, channels: list[str]) -> list[str]:
        """Attempts to remove channels from config, and returns fails"""
        config = self.load_config()
        fail = []
        for channel in channels:
            if channel in config["channels"]:
                config["channels"].remove(channel)
            else:
                fail.append(channel)
        self.update_config(config)
        return fail


class MongoDBUserConfiguration(LocalUserConfiguration):
    """Simplifies interaction with the MongoDB NoSQL database system - overrides methods from class above"""

    def __init__(self, tg_user_id: str):
        """
        :param tg_user_id: The Telegram user ID of the bot user to locate their configuration
        """
        # Initialize LocalUserConfiguration & MongoClient superclasses and connect to database
        super().__init__(tg_user_id=tg_user_id)

        # Additional variables required for MongoDB
        self.filter = {"user_id": self.user_id}

    def whitelist_user(self, is_admin: bool = False, username: str = None):
        """OVERRIDES SUPER - Add necessary files and directories to database for TG user ID"""

        # Return if user data directory already exists
        if self.user_id in get_whitelist():
            return

        # Prepare default user document
        user_document = {"user_id": self.user_id}
        try:
            from datetime import datetime

            # Make default configuration:
            with open(self.default_config_path, "r") as _in:
                default_config = json.loads(_in.read())

            # Add user properties
            default_config["channels"].append(self.user_id)
            if is_admin:
                default_config["is_admin"] = True

            default_config["telegram_id"] = self.user_id
            if username:
                default_config["username"] = username
            default_config["plan"] = "free"
            default_config["max_alerts"] = PLANS.get("free", 3)
            default_config["created_at"] = datetime.utcnow().isoformat()
            default_config["updated_at"] = datetime.utcnow().isoformat()

            user_document["config"] = default_config

            # Make default alerts
            with open(self.default_alerts_path, "r") as _in:
                user_document["alerts"] = json.loads(_in.read())
        except Exception as exc:
            self.blacklist_user()
            raise Exception(f"Could not prepare user document for MongoDB - {exc}")

        # Push new user document to MongoDB
        db_connection.collection.insert_one(user_document)

    def blacklist_user(self):
        """OVERRIDES SUPER - Remove TG user from whitelist"""
        db_connection.collection.delete_one(self.filter)

    def _load_document(self) -> dict:
        if self.user_id not in get_whitelist():
            raise Exception(
                f"Cannot load document - user {self.user_id} is not yet whitelisted"
            )

        return db_connection.collection.find_one(self.filter)

    def load_alerts(self) -> dict:
        """OVERRIDES SUPER - Load the database alert contents and return it in JSON format"""
        if self.user_id not in get_whitelist():
            raise Exception(
                f"Cannot load alerts - user {self.user_id} is not yet whitelisted"
            )

        return db_connection.collection.find_one(self.filter)["alerts"]

    def update_alerts(self, data: dict) -> None:
        """OVERRIDES SUPER - Update the contents of the 'alerts' section of the user document"""
        db_connection.collection.update_one(
            self.filter, {"$set": {"alerts": data}}, upsert=True
        )

    def load_config(self) -> dict:
        """OVERRIDES SUPER - Load the config section of the user document"""
        if self.user_id not in get_whitelist():
            raise Exception(
                f"Cannot load config - user {self.user_id} is not yet whitelisted"
            )

        return db_connection.collection.find_one({"user_id": self.user_id})["config"]

    def update_config(self, data: dict) -> None:
        """OVERRIDES SUPER - Update the config section of the user document"""
        db_connection.collection.update_one(
            self.filter, {"$set": {"config": data}}, upsert=True
        )

    def get_plan(self) -> str:
        """OVERRIDES SUPER - Get the plan from the user document"""
        config = self.load_config()
        return config.get("plan", "free")

    def set_plan(self, plan: str) -> None:
        """OVERRIDES SUPER - Set the plan in the user document"""
        config = self.load_config()
        from datetime import datetime

        config["plan"] = plan
        config["max_alerts"] = PLANS.get(plan, 3)
        config["updated_at"] = datetime.utcnow().isoformat()
        self.update_config(config)


def get_whitelist() -> list:
    if not USE_MONGO_DB:
        if not isdir(WHITELIST_ROOT):
            mkdir(WHITELIST_ROOT)

        return [
            _id for _id in listdir(WHITELIST_ROOT) if isdir(join(WHITELIST_ROOT, _id))
        ]
    else:
        return [user["user_id"] for user in db_connection.collection.find()]
