import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, PropertyResult

logger = logging.getLogger(__name__)


class RealtorScraper(BaseScraper):
    """
    Scraper for Realtor.com property listings.

    Realtor.com has good coverage of recently sold properties
    and foreclosure listings across the US.
    """

    name = "realtor"
    state = ""  # Multi-state
    base_url = "https://www.realtor.com"

    def __init__(self, location: str = "Miami_FL"):
        """
        Initialize Realtor.com scraper.

        Args:
            location: City_State format (e.g., "Miami_FL")
        """
        super().__init__()
        self.location = location.replace(", ", "_").replace(" ", "-")

    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recently sold properties."""
        results = []
        page = await self.new_page()

        try:
            # Realtor.com sold properties URL
            search_url = f"{self.base_url}/realestateandhomes-search/{self.location}/show-recently-sold"

            logger.info(f"[{self.name}] Fetching recent sales: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "realtor_sales")

            # Parse listings
            results = await self._parse_listings(page, "sale")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching sales")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching sales: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} recent sales")
        return results

    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure properties."""
        results = []
        page = await self.new_page()

        try:
            # Realtor.com foreclosure search
            search_url = f"{self.base_url}/realestateandhomes-search/{self.location}/type-single-family-home/fc-foreclosure"

            logger.info(f"[{self.name}] Fetching foreclosures: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "realtor_foreclosures")

            # Parse listings
            results = await self._parse_listings(page, "foreclosure")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching foreclosures")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching foreclosures: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} foreclosures")
        return results

    async def _parse_listings(self, page: Page, record_type: str) -> list[PropertyResult]:
        """Parse Realtor.com property listings."""
        results = []

        # Try multiple selectors for property cards
        card_selectors = [
            "[data-testid='property-card']",
            ".property-card",
            ".PropertyCard",
            "li[data-testid='result-card']",
            ".srp-item",
        ]

        cards = []
        for selector in card_selectors:
            cards = await page.query_selector_all(selector)
            if cards:
                logger.info(f"[{self.name}] Found {len(cards)} listings with {selector}")
                break

        # Fallback: find all listing links
        if not cards:
            cards = await page.query_selector_all("a[href*='/realestateandhomes-detail/']")
            logger.info(f"[{self.name}] Found {len(cards)} listing links")

        for card in cards[:20]:
            try:
                result = await self._parse_listing(card, record_type)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] Error parsing listing: {e}")
                continue

        return results

    async def _parse_listing(self, card, record_type: str) -> Optional[PropertyResult]:
        """Parse a single property listing."""
        # Get link first
        link = card if card.evaluate("el => el.tagName") == "A" else await card.query_selector("a")
        href = await link.get_attribute("href") if link else ""

        if not href or "/realestateandhomes-detail/" not in href:
            # Try to find nested link
            nested_link = await card.query_selector("a[href*='/realestateandhomes-detail/']")
            if nested_link:
                href = await nested_link.get_attribute("href")

        if not href:
            return None

        url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Get card text for parsing
        card_text = await card.inner_text()

        # Extract price
        price_match = re.search(r"\$[\d,]+", card_text)
        price = self.parse_price(price_match.group(0)) if price_match else None

        # Extract address from URL or text
        address = self._extract_address_from_url(href)
        if not address:
            # Try to find address in text
            address_match = re.search(
                r"(\d+\s+[A-Za-z0-9\s]+(?:St|Ave|Blvd|Dr|Rd|Ct|Way|Ln|Pl|Ter)[^,\n]*)",
                card_text,
                re.IGNORECASE
            )
            address = address_match.group(1).strip() if address_match else "Unknown Address"

        # Extract city/state/zip
        location_match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", card_text)
        city = location_match.group(1).strip() if location_match else ""
        state = location_match.group(2) if location_match else ""
        zip_code = location_match.group(3) or "" if location_match else ""

        # Generate parcel ID
        parcel_id = self._extract_id_from_url(href) or self._generate_parcel_id(address)

        # Extract sold date if present
        sold_match = re.search(r"Sold\s+(\d{1,2}/\d{1,2}/\d{4}|\w+\s+\d{1,2},?\s+\d{4})", card_text)
        sold_date = self.parse_date(sold_match.group(1)) if sold_match else None

        return PropertyResult(
            parcel_id=parcel_id,
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            property_type="residential",
            record_type=record_type,
            sale_price=price,
            sale_date=sold_date,
            seller=None,
            buyer=None,
            url=url
        )

    def _extract_address_from_url(self, url: str) -> Optional[str]:
        """Extract address from Realtor.com URL."""
        # URL format: /realestateandhomes-detail/123-Main-St_Miami_FL_33139_M12345-67890
        match = re.search(r"/realestateandhomes-detail/([^_]+)", url)
        if match:
            address_slug = match.group(1)
            # Convert slug to address
            address = address_slug.replace("-", " ")
            return address
        return None

    def _extract_id_from_url(self, url: str) -> Optional[str]:
        """Extract property ID from URL."""
        # Look for M followed by numbers
        match = re.search(r"_M(\d+-\d+)", url)
        if match:
            return match.group(1)
        return None

    def _generate_parcel_id(self, address: str) -> str:
        """Generate a pseudo parcel ID from address."""
        import hashlib
        return hashlib.md5(address.encode()).hexdigest()[:12]
