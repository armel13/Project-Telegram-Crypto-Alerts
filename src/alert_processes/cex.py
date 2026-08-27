import time
from datetime import datetime
import os

from ..user_configuration import (
    LocalUserConfiguration,
    MongoDBUserConfiguration,
    get_whitelist,
)
from ..logger import logger
from ..config import *
from ..utils import get_binance_price_url
from .base import BaseAlertProcess
from ..telegram import TelegramBot
from ..models import BinancePriceResponse
from ..binance_client import fetch_binance_market_data

import requests
from ratelimit import limits, sleep_and_retry


class CEXAlertProcess(BaseAlertProcess):
    def __init__(self, telegram_bot: TelegramBot):
        """
        :param telegram_bot: The Telegram bot instance
        """
        super().__init__(telegram_bot)
        self.polling = False  # Temporary variable to manage alerts

        self.endpoint = get_binance_price_url()

    def poll_user_alerts(self, tg_user_id: str) -> None:
        """
        1. Load the user's configuration
        2. poll all alerts and create posts
        3. Remove alert conditions
        4. Send alerts if found

        :param tg_user_id: The Telegram user ID from the database
        """
        configuration = (
            LocalUserConfiguration(tg_user_id)
            if not USE_MONGO_DB
            else MongoDBUserConfiguration(tg_user_id)
        )
        alerts_database = configuration.load_alerts()
        config = configuration.load_config()

        do_update = False  # If any changes are made, update the database
        post_queue = []
        for pair in alerts_database.copy().keys():

            remove_queue = []
            for alert in alerts_database[pair]:
                if alert["type"] == "s":
                    condition, value, post_string = self.get_simple_indicator(
                        pair, alert
                    )

                    if condition:
                        cooldown = alert.get("trigger", {}).get("cooldown_seconds")
                        last_trigger = alert.get("trigger", {}).get("last_triggered", 0)
                        if int(time.time()) > last_trigger + (cooldown or 0):
                            post_queue.append((post_string, pair, alert))

            for item in remove_queue:
                alerts_database[pair].remove(item)
                if len(alerts_database[pair]) == 0:
                    alerts_database.pop(pair)

        if len(post_queue) > 0:
            self.polling = False
            for post, pair, alert in post_queue:
                logger.info(post)
                status = self.tg_alert(
                    post=post,
                    channel_ids=(
                        config.get("channels")
                        if config.get("channels")
                        else [tg_user_id]
                    ),
                    pair=pair,
                )
                if len(status[0]) > 0:
                    alert["trigger"] = {
                        "cooldown_seconds": alert.get("trigger", {}).get(
                            "cooldown_seconds"
                        ),
                        "last_triggered": int(time.time()),
                    }
                    do_update = True
                    if not alert["trigger"]["cooldown_seconds"]:
                        try:
                            alerts_database[pair].remove(alert)
                            if len(alerts_database[pair]) == 0:
                                alerts_database.pop(pair)
                        except (ValueError, KeyError):
                            pass
                if len(status[1]) > 0:
                    logger.warn(
                        f"Failed to send Telegram alert ({post}) to the following IDs: {status[1]}"
                    )

        if do_update:
            configuration.update_alerts(alerts_database)

        if not self.polling:
            self.polling = True
            logger.info(f"Bot polling for next alert...")

    @sleep_and_retry
    @limits(calls=1, period=CEX_POLLING_PERIOD)
    def poll_all_alerts(self) -> None:
        for user in get_whitelist():
            self.poll_user_alerts(tg_user_id=user)

    def get_simple_indicator(
        self, pair: str, alert: dict, pair_price: float = None
    ) -> tuple[bool, float, str]:
        """
        Accounts for the 3 following simple price movement indicators:
        PCTCHG - Percent change in the price
        ABOVE - Price above the target
        BELOW - Price below the target

        :param pair: The crypto pair
        :param pair_price: The current price of the crypto pair.
                           Get the pair price before calling the self.get_pair_price() function
        :param alert: An alert data dictionary as returned by src.io_handler.UserConfiguration.load_alerts()

        :returns: Tuple:
                  (Boolean) True if the indicator is satisfied, False if not
                  (Float) The current value of the indicator
                  (String) The formatted string to send with alerts
        """
        target = alert["target"]
        # indicator = alert["indicator"]
        comparison = alert["comparison"]
        if pair_price is None:
            pair_price = float(
                fetch_binance_market_data(pair.replace("/", ""))["lastPrice"]
            )

        if comparison == "PCTCHG":
            entry = alert["entry"]
            if pair_price > (entry * (1 + target)):
                pct_chg = ((pair_price - entry) / entry) * 100
                return (
                    True,
                    pct_chg,
                    f"{pair} UP {pct_chg:.1f}% FROM {entry} AT {pair_price}",
                )
            elif pair_price < (entry * (1 - target)):
                pct_chg = ((entry - pair_price) / entry) * 100
                return (
                    True,
                    pct_chg,
                    f"{pair} DOWN {pct_chg:.1f}% FROM {entry} AT {pair_price}",
                )
        elif comparison == "24HRCHG":
            pct_change = float(
                fetch_binance_market_data(pair.replace("/", ""))["priceChangePercent"]
            )
            if abs(pct_change) / 100 >= alert["target"]:
                return (
                    True,
                    pct_change,
                    f"{pair} 24HR CHANGE {pct_change:.1f}% AT {pair_price}",
                )
        elif comparison == "ABOVE":
            if pair_price > target:
                return True, pair_price, f"{pair} ABOVE {target} TARGET AT {pair_price}"
        elif comparison == "BELOW":
            if pair_price < target:
                return True, pair_price, f"{pair} BELOW {target} TARGET AT {pair_price}"

        return False, pair_price, ""

    def tg_alert(self, post: str, channel_ids: list[str], pair: str = None) -> tuple:
        """
        Sends the post (price alert) to each registered user of the Telegram bot

        :param post: A message to send to each registered bot user
        :param channel_ids: All group ids to send the alert to (self.config_client.load_config()['channels'])
        :param pair: The binance pair corresponding to the alert (for showing chart)

        :return: Tuple = ([successful group ids], [unsuccessful group ids])
        """
        post = f"🔔 <b>CEX ALERT:</b> 🔔\n\n" + post
        if pair:
            pair_fmt = pair.replace("/", "_")
            post += f"\n\n<a href='https://www.binance.com/en/trade/{pair_fmt}?type=spot'><b>View {pair} Chart</b></a>"

        post += "\n\n<i>*Not financial advice. Market monitoring only.</i>"

        output = ([], [])
        for g_id in channel_ids:
            try:
                self.telegram_bot.send_message(
                    chat_id=g_id,
                    text=post,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                output[0].append(g_id)
            except:
                output[1].append(g_id)

        return output

    def run(self):
        logger.warn(f"{type(self).__name__} started at {datetime.utcnow()} UTC+0")
        while True:
            try:
                self.poll_all_alerts()
            except NotImplementedError as exc:
                logger.critical(exc_info=exc)
            except KeyboardInterrupt:
                logger.critical("KeyboardInterrupt detected. Exiting...")
                exit(0)
            except Exception as exc:
                logger.critical(
                    f"An error has occurred in the {type(self).__name__} process. Trying again in 15 seconds...",
                    exc_info=exc,
                )
                time.sleep(15)
