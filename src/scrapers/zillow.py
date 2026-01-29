import logging
import re
import json
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, PropertyResult

logger = logging.getLogger(__name__)


class ZillowScraper(BaseScraper):
    """
    Scraper for Zillow.com using their mobile-friendly pages.

    Uses Zillow's less protected endpoints and mobile views
    which are often easier to scrape.
    """

    name = "zillow"
    state = ""
    base_url = "https://www.zillow.com"

    def __init__(self, location: str = "miami-fl"):
        super().__init__()
        self.location = location.lower().replace(", ", "-").replace(" ", "-")

    async def start(self) -> None:
        """Start browser with mobile user agent."""
        from playwright.async_api import async_playwright
        from src.config import HEADLESS, SCREENSHOTS_DIR

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )
        # Use mobile viewport and user agent
        self._context = await self._browser.new_context(
            viewport={"width": 414, "height": 896},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            )
        )
        logger.info(f"[{self.name}] Browser started (mobile mode)")

    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recently sold properties."""
        results = []
        page = await self.new_page()

        try:
            # Zillow recently sold URL
            search_url = f"{self.base_url}/{self.location}/sold/"
            logger.info(f"[{self.name}] Fetching: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "zillow_sold")

            # Parse results
            results = await self._parse_listings(page, "sale")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout")
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} recent sales")
        return results

    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure properties."""
        results = []
        page = await self.new_page()

        try:
            # Zillow foreclosure URL
            search_url = f"{self.base_url}/{self.location}/foreclosures/"
            logger.info(f"[{self.name}] Fetching foreclosures: {search_url}")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "zillow_foreclosures")

            results = await self._parse_listings(page, "foreclosure")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout")
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} foreclosures")
        return results

    async def _parse_listings(self, page: Page, record_type: str) -> list[PropertyResult]:
        """Parse Zillow property listings."""
        results = []

        # Get page content and look for JSON data
        content = await page.content()

        # Zillow often embeds listing data in script tags
        script_data = await page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[type="application/json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (data && (data.cat1 || data.searchResults || data.listResults)) {
                            return data;
                        }
                    } catch (e) {}
                }

                // Also check for __NEXT_DATA__
                const nextData = document.getElementById('__NEXT_DATA__');
                if (nextData) {
                    try {
                        return JSON.parse(nextData.textContent);
                    } catch (e) {}
                }

                return null;
            }
        """)

        if script_data:
            results = self._parse_json_data(script_data, record_type)
            if results:
                return results

        # Fallback: parse DOM
        cards = await page.query_selector_all(
            "[data-test='property-card'], .list-card, .property-card, article"
        )

        logger.info(f"[{self.name}] Found {len(cards)} property cards in DOM")

        for card in cards[:20]:
            try:
                result = await self._parse_card(card, record_type)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] Card parse error: {e}")

        return results

    def _parse_json_data(self, data: dict, record_type: str) -> list[PropertyResult]:
        """Parse listings from Zillow's JSON data."""
        results = []

        # Try different data structures Zillow uses
        listings = []

        if isinstance(data, dict):
            # Check various paths where listings might be
            if "cat1" in data:
                listings = data.get("cat1", {}).get("searchResults", {}).get("listResults", [])
            elif "searchResults" in data:
                listings = data.get("searchResults", {}).get("listResults", [])
            elif "listResults" in data:
                listings = data.get("listResults", [])
            elif "props" in data:
                # __NEXT_DATA__ format
                page_props = data.get("props", {}).get("pageProps", {})
                listings = page_props.get("searchPageState", {}).get("cat1", {}).get("searchResults", {}).get("listResults", [])

        for listing in listings[:20]:
            try:
                result = self._parse_listing_json(listing, record_type)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] JSON parse error: {e}")

        return results

    def _parse_listing_json(self, listing: dict, record_type: str) -> Optional[PropertyResult]:
        """Parse a single listing from JSON."""
        # Get address
        address = listing.get("address", "")
        if not address:
            address_data = listing.get("addressInfo", {})
            street = address_data.get("streetAddress", "")
            city = address_data.get("city", "")
            state = address_data.get("state", "")
            zipcode = address_data.get("zipcode", "")
            address = street

        if not address:
            return None

        # Get price
        price = listing.get("price", 0)
        if isinstance(price, str):
            price = self.parse_price(price)

        # Get details
        zpid = str(listing.get("zpid", listing.get("id", "")))
        city = listing.get("addressCity", "") or listing.get("city", "")
        state = listing.get("addressState", "") or listing.get("state", "")
        zipcode = listing.get("addressZipcode", "") or listing.get("zipcode", "")

        # Build URL
        detail_url = listing.get("detailUrl", "")
        if not detail_url and zpid:
            detail_url = f"{self.base_url}/homedetails/{zpid}_zpid/"

        return PropertyResult(
            parcel_id=zpid or self._generate_parcel_id(address),
            address=address,
            city=city,
            state=state,
            zip_code=zipcode,
            property_type="residential",
            record_type=record_type,
            sale_price=price if price else None,
            sale_date=listing.get("soldDate"),
            seller=None,
            buyer=None,
            url=detail_url if detail_url.startswith("http") else f"{self.base_url}{detail_url}",
            raw_data=listing
        )

    async def _parse_card(self, card, record_type: str) -> Optional[PropertyResult]:
        """Parse a property card from DOM."""
        # Get link
        link = await card.query_selector("a[href*='homedetails'], a[href*='zpid']")
        if not link:
            return None

        href = await link.get_attribute("href")
        if not href:
            return None

        url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Get text content
        text = await card.inner_text()

        # Extract price
        price_match = re.search(r"\$[\d,]+", text)
        price = self.parse_price(price_match.group(0)) if price_match else None

        # Extract address
        address_match = re.search(
            r"(\d+\s+[A-Za-z0-9\s]+(?:St|Ave|Blvd|Dr|Rd|Ct|Way|Ln|Pl|Ter)[^,\n]*)",
            text,
            re.IGNORECASE
        )
        address = address_match.group(1).strip() if address_match else "Unknown"

        # Extract zpid from URL
        zpid_match = re.search(r"(\d+)_zpid", url)
        zpid = zpid_match.group(1) if zpid_match else self._generate_parcel_id(address)

        # Extract location
        loc_match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", text)
        city = loc_match.group(1).strip() if loc_match else ""
        state = loc_match.group(2) if loc_match else ""
        zipcode = loc_match.group(3) or "" if loc_match else ""

        return PropertyResult(
            parcel_id=zpid,
            address=address,
            city=city,
            state=state,
            zip_code=zipcode,
            property_type="residential",
            record_type=record_type,
            sale_price=price,
            sale_date=None,
            seller=None,
            buyer=None,
            url=url
        )

    def _generate_parcel_id(self, address: str) -> str:
        import hashlib
        return hashlib.md5(address.encode()).hexdigest()[:12]
