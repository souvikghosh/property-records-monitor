from abc import ABC, abstractmethod
import logging

from src.database import PropertyRecord

logger = logging.getLogger(__name__)


class BaseNotifier(ABC):
    """Abstract base class for notification handlers."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this notifier is properly configured."""
        pass

    @abstractmethod
    async def notify(self, records: list[PropertyRecord]) -> bool:
        """
        Send notification for new property records.

        Args:
            records: List of new property records to notify about

        Returns:
            True if notification was sent successfully
        """
        pass

    def format_record(self, record: PropertyRecord) -> str:
        """Format a single property record for display."""
        lines = [
            f"**{record.address}**",
            f"{record.city}, {record.state} {record.zip_code}",
            f"Price: {record.formatted_price}",
            f"Type: {record.record_type.title()}",
        ]

        if record.sale_date:
            lines.append(f"Date: {record.sale_date}")
        if record.buyer:
            lines.append(f"Buyer: {record.buyer}")
        if record.seller:
            lines.append(f"Seller: {record.seller}")

        lines.append(f"County: {record.county}")
        lines.append(f"URL: {record.url}")

        return "\n".join(lines)

    def format_summary(self, records: list[PropertyRecord]) -> str:
        """Format summary of multiple records."""
        total = len(records)
        foreclosures = sum(1 for r in records if r.record_type == "foreclosure")
        sales = sum(1 for r in records if r.record_type == "sale")

        parts = [f"{total} new properties"]
        if sales:
            parts.append(f"{sales} sales")
        if foreclosures:
            parts.append(f"{foreclosures} foreclosures")

        return " | ".join(parts)
