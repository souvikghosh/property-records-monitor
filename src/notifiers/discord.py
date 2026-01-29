import logging

import aiohttp

from src.config import DISCORD_WEBHOOK_URL
from src.database import PropertyRecord
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    """Send property notifications via Discord webhook."""

    name = "discord"

    def is_configured(self) -> bool:
        return bool(DISCORD_WEBHOOK_URL)

    async def notify(self, records: list[PropertyRecord]) -> bool:
        if not self.is_configured():
            logger.warning(f"[{self.name}] Not configured, skipping")
            return False

        if not records:
            return True

        try:
            embeds = []

            for record in records[:10]:  # Discord max 10 embeds
                # Color based on record type
                color = 0x00FF00 if record.record_type == "sale" else 0xFF6600  # Green for sales, orange for foreclosures

                embed = {
                    "title": f"🏠 {record.address}",
                    "url": record.url,
                    "color": color,
                    "fields": [
                        {
                            "name": "Price",
                            "value": record.formatted_price,
                            "inline": True
                        },
                        {
                            "name": "Type",
                            "value": record.record_type.title(),
                            "inline": True
                        },
                        {
                            "name": "Location",
                            "value": f"{record.city}, {record.state} {record.zip_code}",
                            "inline": True
                        },
                    ]
                }

                if record.sale_date:
                    embed["fields"].append({
                        "name": "Date",
                        "value": record.sale_date,
                        "inline": True
                    })

                embed["fields"].append({
                    "name": "Source",
                    "value": record.county.replace("_", " ").title(),
                    "inline": True
                })

                embeds.append(embed)

            payload = {
                "content": f"**Property Alert:** {self.format_summary(records)}",
                "embeds": embeds
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DISCORD_WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status < 300:
                        logger.info(f"[{self.name}] Discord notification sent")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"[{self.name}] Discord failed: {response.status} - {text}")
                        return False

        except Exception as e:
            logger.error(f"[{self.name}] Discord error: {e}")
            return False
