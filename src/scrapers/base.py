from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging
import re

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from src.database import PropertyRecord
from src.config import HEADLESS, SCREENSHOTS_DIR, MIN_PRICE, MAX_PRICE, ZIP_CODES, PROPERTY_TYPES

logger = logging.getLogger(__name__)


@dataclass
class PropertyResult:
    """Raw property result before database storage."""
    parcel_id: str
    address: str
    city: str
    state: str
    zip_code: str
    property_type: str  # residential, commercial, land
    record_type: str  # sale, foreclosure, lien, transfer
    sale_price: Optional[int]
    sale_date: Optional[str]
    seller: Optional[str]
    buyer: Optional[str]
    url: str
    raw_data: Optional[dict] = None


class BaseScraper(ABC):
    """Abstract base class for county property scrapers."""

    name: str = "base"
    state: str = ""
    base_url: str = ""

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self) -> None:
        """Start the browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        logger.info(f"[{self.name}] Browser started")

    async def stop(self) -> None:
        """Stop the browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info(f"[{self.name}] Browser stopped")

    async def new_page(self) -> Page:
        """Create a new browser page."""
        return await self._context.new_page()

    async def screenshot(self, page: Page, name: str) -> Path:
        """Take a screenshot of the current page."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.name}_{name}_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"[{self.name}] Screenshot saved: {filepath}")
        return filepath

    def matches_filters(self, result: PropertyResult) -> bool:
        """Check if a property result matches configured filters."""
        # Price filter
        if result.sale_price:
            if MIN_PRICE and result.sale_price < MIN_PRICE:
                return False
            if MAX_PRICE and result.sale_price > MAX_PRICE:
                return False

        # Zip code filter
        if ZIP_CODES and result.zip_code:
            if result.zip_code not in ZIP_CODES:
                return False

        # Property type filter
        if PROPERTY_TYPES and "all" not in PROPERTY_TYPES:
            if result.record_type not in PROPERTY_TYPES and result.property_type not in PROPERTY_TYPES:
                return False

        return True

    @abstractmethod
    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recent property sales."""
        pass

    @abstractmethod
    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure listings."""
        pass

    async def fetch_all(self) -> list[PropertyResult]:
        """Fetch all property types."""
        results = []

        try:
            sales = await self.fetch_recent_sales()
            results.extend(sales)
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching sales: {e}")

        try:
            foreclosures = await self.fetch_foreclosures()
            results.extend(foreclosures)
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching foreclosures: {e}")

        # Apply filters
        filtered = [r for r in results if self.matches_filters(r)]
        logger.info(f"[{self.name}] {len(filtered)}/{len(results)} results match filters")

        return filtered

    def to_property_record(self, result: PropertyResult) -> PropertyRecord:
        """Convert a PropertyResult to a PropertyRecord."""
        import json
        now = datetime.utcnow()
        return PropertyRecord(
            id=None,
            county=self.name,
            parcel_id=result.parcel_id,
            address=result.address,
            city=result.city,
            state=result.state or self.state,
            zip_code=result.zip_code,
            property_type=result.property_type,
            record_type=result.record_type,
            sale_price=result.sale_price,
            sale_date=result.sale_date,
            seller=result.seller,
            buyer=result.buyer,
            url=result.url,
            raw_data=json.dumps(result.raw_data) if result.raw_data else None,
            first_seen=now,
            last_seen=now,
            notified=False
        )

    @staticmethod
    def parse_price(price_str: str) -> Optional[int]:
        """Parse price string to integer."""
        if not price_str:
            return None
        # Remove $ , and other non-numeric chars
        cleaned = re.sub(r"[^\d]", "", price_str)
        try:
            return int(cleaned) if cleaned else None
        except ValueError:
            return None

    @staticmethod
    def parse_date(date_str: str) -> Optional[str]:
        """Parse date string to ISO format."""
        if not date_str:
            return None

        # Common date patterns
        patterns = [
            (r"(\d{1,2})/(\d{1,2})/(\d{4})", "%m/%d/%Y"),
            (r"(\d{1,2})-(\d{1,2})-(\d{4})", "%m-%d-%Y"),
            (r"(\d{4})-(\d{1,2})-(\d{1,2})", "%Y-%m-%d"),
            (r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", "%B %d %Y"),
        ]

        for pattern, fmt in patterns:
            if re.match(pattern, date_str.strip()):
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

        return date_str  # Return as-is if can't parse
