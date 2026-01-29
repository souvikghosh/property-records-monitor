import logging
import re
import json
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, PropertyResult

logger = logging.getLogger(__name__)


class RedfinScraper(BaseScraper):
    """
    Scraper for Redfin.com property listings.

    Redfin provides recent sales data and foreclosure listings.
    Works across all US markets.
    """

    name = "redfin"
    state = ""  # Multi-state
    base_url = "https://www.redfin.com"

    def __init__(self, location: str = "Miami, FL"):
        """
        Initialize Redfin scraper.

        Args:
            location: City, State to search (e.g., "Miami, FL")
        """
        super().__init__()
        self.location = location

    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recently sold properties."""
        results = []
        page = await self.new_page()

        try:
            # Build Redfin sold search URL
            location_slug = self.location.lower().replace(", ", "-").replace(" ", "-")
            search_url = f"{self.base_url}/city/{location_slug}/filter/include=sold-3mo"

            logger.info(f"[{self.name}] Fetching recent sales: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)  # Let React render

            await self.screenshot(page, "redfin_sales")

            # Parse property cards
            results = await self._parse_property_cards(page, "sale")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching sales")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching sales: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} recent sales")
        return results

    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure/bank-owned properties."""
        results = []
        page = await self.new_page()

        try:
            # Redfin foreclosure filter
            location_slug = self.location.lower().replace(", ", "-").replace(" ", "-")
            search_url = f"{self.base_url}/city/{location_slug}/filter/property-type=house,foreclosure=true"

            logger.info(f"[{self.name}] Fetching foreclosures: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "redfin_foreclosures")

            # Parse property cards
            results = await self._parse_property_cards(page, "foreclosure")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching foreclosures")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching foreclosures: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} foreclosures")
        return results

    async def _parse_property_cards(self, page: Page, record_type: str) -> list[PropertyResult]:
        """Parse Redfin property cards."""
        results = []

        # Redfin uses various card selectors
        card_selectors = [
            "[data-rf-test-id='home-card']",
            ".HomeCard",
            ".home-card",
            ".MapHomeCard",
            "article[class*='HomeCard']",
        ]

        cards = []
        for selector in card_selectors:
            cards = await page.query_selector_all(selector)
            if cards:
                logger.info(f"[{self.name}] Found {len(cards)} cards with {selector}")
                break

        for card in cards[:20]:
            try:
                result = await self._parse_card(card, record_type)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] Error parsing card: {e}")
                continue

        return results

    async def _parse_card(self, card, record_type: str) -> Optional[PropertyResult]:
        """Parse a single property card."""
        # Get price
        price_el = await card.query_selector(
            "[data-rf-test-id='home-card-price'], .price, .homecardV2Price"
        )
        price_text = await price_el.inner_text() if price_el else ""
        price = self.parse_price(price_text)

        # Get address
        address_el = await card.query_selector(
            "[data-rf-test-id='home-card-street-address'], .address, .homeAddress"
        )
        address = await address_el.inner_text() if address_el else ""

        if not address:
            return None

        # Get city/state/zip
        location_el = await card.query_selector(
            "[data-rf-test-id='home-card-city-state-zip'], .cityStateZip"
        )
        location_text = await location_el.inner_text() if location_el else ""
        city, state, zip_code = self._parse_location(location_text)

        # Get link
        link = await card.query_selector("a[href*='/home/']")
        href = await link.get_attribute("href") if link else ""
        url = href if href.startswith("http") else f"{self.base_url}{href}" if href else self.base_url

        # Generate parcel ID from URL or address
        parcel_id = self._extract_mls_from_url(url) or self._generate_parcel_id(address)

        # Get sold date if available
        sold_el = await card.query_selector(".sold-date, [class*='soldDate']")
        sold_date = None
        if sold_el:
            sold_text = await sold_el.inner_text()
            sold_date = self.parse_date(sold_text)

        return PropertyResult(
            parcel_id=parcel_id,
            address=address.strip(),
            city=city or "",
            state=state or "",
            zip_code=zip_code or "",
            property_type="residential",
            record_type=record_type,
            sale_price=price,
            sale_date=sold_date,
            seller=None,
            buyer=None,
            url=url
        )

    def _parse_location(self, location_text: str) -> tuple[str, str, str]:
        """Parse city, state, zip from location text."""
        city, state, zip_code = "", "", ""

        if not location_text:
            return city, state, zip_code

        # Format: "Miami, FL 33139" or "Miami Beach, FL"
        parts = location_text.strip().split(",")
        if len(parts) >= 1:
            city = parts[0].strip()

        if len(parts) >= 2:
            state_zip = parts[1].strip()
            match = re.match(r"([A-Z]{2})\s*(\d{5})?", state_zip)
            if match:
                state = match.group(1)
                zip_code = match.group(2) or ""

        return city, state, zip_code

    def _extract_mls_from_url(self, url: str) -> Optional[str]:
        """Extract MLS number from Redfin URL."""
        # Redfin URLs often contain property ID
        match = re.search(r"/home/(\d+)", url)
        return match.group(1) if match else None

    def _generate_parcel_id(self, address: str) -> str:
        """Generate a pseudo parcel ID from address."""
        import hashlib
        return hashlib.md5(address.encode()).hexdigest()[:12]
