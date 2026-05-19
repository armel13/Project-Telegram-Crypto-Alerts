# Security Policy

## Supported Versions

Currently, only the latest version of this software is supported with security updates.

## Reporting a Vulnerability

If you discover a security vulnerability within this project, please report it via email to the maintainers instead of opening a public issue. We will make every effort to acknowledge and resolve the vulnerability in a timely manner.

## Best Practices

When deploying this project, ensure that you follow these security best practices:
1. **Never commit `.env` files or hardcode API keys/secrets.** Use `.env` files exclusively for local and production environment configuration.
2. Ensure MongoDB deployments are secured with proper authentication, network firewalls, and are not unnecessarily exposed to the public internet.
3. The Telegram bot token is sensitive; do not share it. If it is compromised, revoke it immediately via the Telegram BotFather.
4. Keep Docker and the host server's OS up to date with the latest security patches.
