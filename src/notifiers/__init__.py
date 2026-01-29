from .base import BaseNotifier
from .discord import DiscordNotifier
from .email import EmailNotifier
from .webhook import WebhookNotifier

NOTIFIERS = [
    DiscordNotifier(),
    EmailNotifier(),
    WebhookNotifier(),
]


async def notify_all(records: list) -> dict[str, bool]:
    """Send notifications through all configured notifiers."""
    results = {}

    for notifier in NOTIFIERS:
        if notifier.is_configured():
            results[notifier.name] = await notifier.notify(records)

    return results


__all__ = [
    "BaseNotifier",
    "DiscordNotifier",
    "EmailNotifier",
    "WebhookNotifier",
    "NOTIFIERS",
    "notify_all",
]
