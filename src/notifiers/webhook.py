import logging

import aiohttp

from src.config import WEBHOOK_URL
from src.database import PropertyRecord
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class WebhookNotifier(BaseNotifier):
    """Send property notifications via generic webhook."""

    name = "webhook"

    def is_configured(self) -> bool:
        return bool(WEBHOOK_URL)

    async def notify(self, records: list[PropertyRecord]) -> bool:
        if not self.is_configured():
            logger.warning(f"[{self.name}] Not configured, skipping")
            return False

        if not records:
            return True

        try:
            payload = {
                "event": "new_properties",
                "count": len(records),
                "summary": self.format_summary(records),
                "properties": [
                    {
                        "parcel_id": r.parcel_id,
                        "address": r.address,
                        "city": r.city,
                        "state": r.state,
                        "zip_code": r.zip_code,
                        "price": r.sale_price,
                        "price_formatted": r.formatted_price,
                        "record_type": r.record_type,
                        "property_type": r.property_type,
                        "sale_date": r.sale_date,
                        "seller": r.seller,
                        "buyer": r.buyer,
                        "county": r.county,
                        "url": r.url,
                        "first_seen": r.first_seen.isoformat(),
                    }
                    for r in records
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    WEBHOOK_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status < 300:
                        logger.info(f"[{self.name}] Webhook sent")
                        return True
                    else:
                        logger.error(f"[{self.name}] Webhook failed: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"[{self.name}] Webhook error: {e}")
            return False
