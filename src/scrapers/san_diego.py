import logging
import re
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, PropertyResult

logger = logging.getLogger(__name__)


class SanDiegoCountyScraper(BaseScraper):
    """
    Scraper for San Diego County, California property records.

    Uses multiple sources:
    1. SANDAG Property Lookup - GIS-based property search
    2. SD County Assessor - Tax and assessment data
    """

    name = "san_diego"
    state = "CA"
    base_url = "https://arcc.sdcounty.ca.gov"
    # Direct links from the assessor site
    property_info_url = "https://arcc.sdcounty.ca.gov/divisions/assessor-services/property-information"
    record_search_url = "https://arcc.sdcounty.ca.gov/divisions/recording/official-record-search"

    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recent property sales from property info page."""
        results = []
        page = await self.new_page()

        try:
            # Go directly to property information page
            logger.info(f"[{self.name}] Navigating to property information")
            await page.goto(self.property_info_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            await self.screenshot(page, "sd_property_info")

            # Look for links to property lookup tools
            lookup_links = await page.query_selector_all(
                "a[href*='lookup'], a[href*='search'], a[href*='parcel'], "
                "a:has-text('Look Up'), a:has-text('Search'), a:has-text('Find')"
            )

            for link in lookup_links[:3]:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    logger.info(f"[{self.name}] Found link: {text} -> {href}")

                    if href and ("lookup" in href.lower() or "search" in href.lower()):
                        # Try this link
                        await link.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        await self.screenshot(page, "sd_lookup_page")

                        results = await self._search_properties(page, "sale")
                        if results:
                            break
                except Exception as e:
                    logger.warning(f"[{self.name}] Link error: {e}")
                    continue

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout")
            await self.screenshot(page, "sd_timeout")
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
            await self.screenshot(page, "sd_error")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} total sales")
        return results

    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure notices from official record search."""
        results = []
        page = await self.new_page()

        try:
            # Go directly to record search page
            logger.info(f"[{self.name}] Navigating to official record search")
            await page.goto(self.record_search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            await self.screenshot(page, "sd_record_search")

            # Look for links to document search
            search_links = await page.query_selector_all(
                "a[href*='search'], a[href*='record'], a:has-text('Search'), "
                "a:has-text('Document'), a:has-text('Official')"
            )

            for link in search_links[:3]:
                try:
                    href = await link.get_attribute("href")
                    text = await link.inner_text()
                    logger.info(f"[{self.name}] Found record link: {text}")

                    if href and "search" in href.lower():
                        await link.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        await self.screenshot(page, "sd_doc_search")

                        # Try to search for Notice of Default
                        results = await self._search_foreclosure_docs(page)
                        if results:
                            break
                except Exception as e:
                    logger.warning(f"[{self.name}] Record link error: {e}")

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout")
        except Exception as e:
            logger.error(f"[{self.name}] Error: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} foreclosures")
        return results

    async def _search_foreclosure_docs(self, page: Page) -> list[PropertyResult]:
        """Search for foreclosure documents."""
        results = []

        # Look for document type dropdown
        doc_type = await page.query_selector(
            "select[name*='type'], select[name*='doc'], select[id*='type']"
        )

        if doc_type:
            # Try to select foreclosure-related document type
            options = await doc_type.query_selector_all("option")
            for opt in options:
                text = await opt.inner_text()
                if any(kw in text.lower() for kw in ["default", "foreclosure", "trustee", "sale"]):
                    value = await opt.get_attribute("value")
                    await doc_type.select_option(value)
                    logger.info(f"[{self.name}] Selected doc type: {text}")

                    # Submit search
                    submit = await page.query_selector("button[type='submit'], input[type='submit']")
                    if submit:
                        await submit.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)

                    results = await self._parse_property_listings(page, "foreclosure")
                    break

        return results

    async def _fetch_sandag_properties(self) -> list[PropertyResult]:
        """Fetch properties from SANDAG GIS lookup."""
        results = []
        page = await self.new_page()

        try:
            logger.info(f"[{self.name}] Trying SANDAG property lookup")
            await page.goto(self.sandag_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await self.screenshot(page, "sd_sandag")

            # SANDAG has an interactive map - look for search input
            search_input = await page.query_selector(
                "input[type='text'], input[placeholder*='address'], input[placeholder*='search'], #search"
            )

            if search_input:
                # Search for a sample San Diego address
                await search_input.fill("San Diego CA")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)

                await self.screenshot(page, "sd_sandag_results")

                # Parse results
                results = await self._parse_property_listings(page, "sale")

        except Exception as e:
            logger.warning(f"[{self.name}] SANDAG error: {e}")
        finally:
            await page.close()

        return results

    async def _search_properties(self, page: Page, record_type: str) -> list[PropertyResult]:
        """Search for properties on current page."""
        results = []

        # Look for search input
        search_input = await page.query_selector(
            "input[type='text'], input[type='search'], input[name*='address'], "
            "input[name*='search'], input[placeholder*='address']"
        )

        if search_input:
            # Try searching for common San Diego area
            await search_input.fill("92101")  # Downtown San Diego zip
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.wait_for_timeout(2000)

            await self.screenshot(page, "sd_search_results")

        # Parse results
        results = await self._parse_property_listings(page, record_type)

        return results

    async def _parse_property_listings(self, page: Page, record_type: str) -> list[PropertyResult]:
        """Parse property listings from page."""
        results = []

        # Try to find data tables first
        tables = await page.query_selector_all("table")

        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 2:
                continue

            # Check if this looks like property data
            header = await rows[0].inner_text() if rows else ""
            if not any(h in header.lower() for h in ["address", "parcel", "apn", "price", "property"]):
                continue

            logger.info(f"[{self.name}] Found property table with {len(rows)} rows")

            for row in rows[1:21]:
                result = await self._parse_table_row(row, record_type)
                if result:
                    results.append(result)

            if results:
                break

        # Fallback: look for property cards/divs
        if not results:
            cards = await page.query_selector_all(
                "[class*='property'], [class*='result'], [class*='listing'], "
                "[data-property], article, .card"
            )

            for card in cards[:20]:
                text = await card.inner_text()
                # Filter out navigation/header elements
                if len(text) < 20 or len(text) > 1000:
                    continue
                if any(skip in text.lower() for skip in ["menu", "navigation", "footer", "copyright"]):
                    continue

                result = await self._parse_card(card, record_type)
                if result:
                    results.append(result)

        return results

    async def _parse_table_row(self, row, record_type: str) -> Optional[PropertyResult]:
        """Parse a table row into a PropertyResult."""
        cells = await row.query_selector_all("td")
        if len(cells) < 2:
            return None

        texts = []
        for cell in cells:
            text = await cell.inner_text()
            texts.append(text.strip())

        # Try to extract data
        address = ""
        parcel_id = ""
        price = None
        sale_date = None

        for text in texts:
            # Address
            if re.search(r"\d+\s+[A-Za-z]", text) and len(text) > 10 and not address:
                address = text

            # Parcel ID (San Diego format: XXX-XXX-XX-XX)
            parcel_match = re.search(r"(\d{3}-\d{3}-\d{2}-\d{2})", text)
            if parcel_match:
                parcel_id = parcel_match.group(1)

            # Price
            if "$" in text:
                price = self.parse_price(text)

            # Date
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", text)
            if date_match:
                sale_date = self.parse_date(date_match.group(1))

        if not address and not parcel_id:
            return None

        link = await row.query_selector("a")
        href = await link.get_attribute("href") if link else ""
        url = href if href.startswith("http") else f"{self.base_url}{href}" if href else self.base_url

        city, zip_code = self._parse_location(address)

        return PropertyResult(
            parcel_id=parcel_id or self._generate_id(address),
            address=address or f"Parcel {parcel_id}",
            city=city or "San Diego",
            state="CA",
            zip_code=zip_code or "",
            property_type="residential",
            record_type=record_type,
            sale_price=price,
            sale_date=sale_date,
            seller=None,
            buyer=None,
            url=url
        )

    async def _parse_card(self, card, record_type: str) -> Optional[PropertyResult]:
        """Parse a property card element."""
        text = await card.inner_text()

        # Extract address
        address_match = re.search(
            r"(\d+\s+[A-Za-z0-9\s]+(?:St|Ave|Blvd|Dr|Rd|Ct|Way|Ln|Pl|Ter|Circle|Cir)[^,\n]*)",
            text, re.IGNORECASE
        )
        if not address_match:
            return None

        address = address_match.group(1).strip()

        # Extract parcel
        parcel_match = re.search(r"(\d{3}-\d{3}-\d{2}-\d{2})", text)
        parcel_id = parcel_match.group(1) if parcel_match else self._generate_id(address)

        # Extract price
        price_match = re.search(r"\$[\d,]+", text)
        price = self.parse_price(price_match.group(0)) if price_match else None

        # Extract date
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", text)
        sale_date = self.parse_date(date_match.group(1)) if date_match else None

        # Get link
        link = await card.query_selector("a")
        href = await link.get_attribute("href") if link else ""
        url = href if href.startswith("http") else f"{self.base_url}{href}" if href else self.base_url

        city, zip_code = self._parse_location(address)

        return PropertyResult(
            parcel_id=parcel_id,
            address=address,
            city=city or "San Diego",
            state="CA",
            zip_code=zip_code or "",
            property_type="residential",
            record_type=record_type,
            sale_price=price,
            sale_date=sale_date,
            seller=None,
            buyer=None,
            url=url
        )

    def _parse_location(self, address: str) -> tuple[Optional[str], Optional[str]]:
        """Extract city and zip from address."""
        city = None
        zip_code = None

        # San Diego area cities
        cities = [
            "San Diego", "La Jolla", "Chula Vista", "Oceanside", "Escondido",
            "Carlsbad", "El Cajon", "Vista", "San Marcos", "Encinitas",
            "National City", "La Mesa", "Santee", "Poway", "Del Mar",
            "Coronado", "Imperial Beach", "Solana Beach", "Lemon Grove",
            "Pacific Beach", "Ocean Beach", "Point Loma", "Hillcrest"
        ]

        for c in cities:
            if c.lower() in address.lower():
                city = c
                break

        # San Diego zips start with 92
        zip_match = re.search(r"(92\d{3})", address)
        if zip_match:
            zip_code = zip_match.group(1)

        return city, zip_code

    def _generate_id(self, text: str) -> str:
        """Generate a pseudo ID from text."""
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()[:12]
