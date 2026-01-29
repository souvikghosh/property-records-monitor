import logging
import re
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseScraper, PropertyResult

logger = logging.getLogger(__name__)


class MiamiDadeScraper(BaseScraper):
    """
    Scraper for Miami-Dade County, Florida property records.

    Uses the Miami-Dade Property Appraiser website for sales data
    and the Clerk of Courts for foreclosures.
    """

    name = "miami_dade"
    state = "FL"
    base_url = "https://www.miamidade.gov/pa"
    clerk_url = "https://www.miamidade.gov/clerk"

    async def fetch_recent_sales(self) -> list[PropertyResult]:
        """Fetch recent property sales from the Property Appraiser."""
        results = []
        page = await self.new_page()

        try:
            # Go to property search
            search_url = f"{self.base_url}/property_search.asp"
            logger.info(f"[{self.name}] Fetching recent sales")

            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # Take screenshot for debugging
            await self.screenshot(page, "sales_page")

            # The Miami-Dade PA site has a recent sales search
            # Try to find and use it
            recent_sales_link = await page.query_selector(
                "a[href*='recent'], a[href*='sales'], a:has-text('Recent Sales')"
            )

            if recent_sales_link:
                await recent_sales_link.click()
                await page.wait_for_load_state("networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

            # Parse results table
            results = await self._parse_sales_table(page)

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching sales")
            await self.screenshot(page, "sales_timeout")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching sales: {e}")
            await self.screenshot(page, "sales_error")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} sales")
        return results

    async def fetch_foreclosures(self) -> list[PropertyResult]:
        """Fetch foreclosure listings from Clerk of Courts."""
        results = []
        page = await self.new_page()

        try:
            # Miami-Dade Clerk has foreclosure auction listings
            foreclosure_url = "https://www.miamidade.gov/clerk/foreclosure-sales.asp"
            logger.info(f"[{self.name}] Fetching foreclosures")

            await page.goto(foreclosure_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            await self.screenshot(page, "foreclosures_page")

            # Parse foreclosure listings
            results = await self._parse_foreclosure_table(page)

        except PlaywrightTimeout:
            logger.error(f"[{self.name}] Timeout fetching foreclosures")
        except Exception as e:
            logger.error(f"[{self.name}] Error fetching foreclosures: {e}")
        finally:
            await page.close()

        logger.info(f"[{self.name}] Found {len(results)} foreclosures")
        return results

    async def _parse_sales_table(self, page: Page) -> list[PropertyResult]:
        """Parse sales results from table."""
        results = []

        # Try to find results table
        tables = await page.query_selector_all("table")

        for table in tables:
            rows = await table.query_selector_all("tr")

            for row in rows[1:21]:  # Skip header, limit to 20
                try:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 4:
                        continue

                    # Extract data from cells (format varies by site)
                    address = await self._get_cell_text(cells, 0)
                    if not address or len(address) < 5:
                        continue

                    parcel_id = await self._get_cell_text(cells, 1) or self._generate_parcel_id(address)
                    price_text = await self._get_cell_text(cells, 2)
                    date_text = await self._get_cell_text(cells, 3)

                    # Try to get link
                    link = await row.query_selector("a")
                    href = await link.get_attribute("href") if link else ""
                    url = href if href.startswith("http") else f"{self.base_url}/{href}" if href else self.base_url

                    # Parse address parts
                    city, zip_code = self._parse_address_parts(address)

                    results.append(PropertyResult(
                        parcel_id=parcel_id,
                        address=address,
                        city=city or "Miami",
                        state="FL",
                        zip_code=zip_code or "",
                        property_type="residential",
                        record_type="sale",
                        sale_price=self.parse_price(price_text),
                        sale_date=self.parse_date(date_text),
                        seller=None,
                        buyer=None,
                        url=url
                    ))

                except Exception as e:
                    logger.warning(f"[{self.name}] Error parsing row: {e}")
                    continue

        return results

    async def _parse_foreclosure_table(self, page: Page) -> list[PropertyResult]:
        """Parse foreclosure listings."""
        results = []

        # Look for foreclosure listing elements
        items = await page.query_selector_all(
            "table tr, .foreclosure-item, .listing-item, article"
        )

        for item in items[:20]:
            try:
                # Get all text content
                text = await item.inner_text()

                # Skip if too short or looks like header
                if len(text) < 20 or "address" in text.lower()[:50]:
                    continue

                # Try to extract address
                address_match = re.search(
                    r"(\d+\s+[A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Ct|Way|Ln|Pl)[^,]*)",
                    text,
                    re.IGNORECASE
                )
                if not address_match:
                    continue

                address = address_match.group(1).strip()

                # Try to extract case number as parcel ID
                case_match = re.search(r"(\d{4}-\d+-\w+|\d{2}-\d+)", text)
                parcel_id = case_match.group(1) if case_match else self._generate_parcel_id(address)

                # Try to extract price
                price_match = re.search(r"\$[\d,]+", text)
                price = self.parse_price(price_match.group(0)) if price_match else None

                # Try to extract date
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
                sale_date = self.parse_date(date_match.group(1)) if date_match else None

                # Get link
                link = await item.query_selector("a")
                href = await link.get_attribute("href") if link else ""
                url = href if href.startswith("http") else f"{self.clerk_url}/{href}" if href else self.clerk_url

                city, zip_code = self._parse_address_parts(address)

                results.append(PropertyResult(
                    parcel_id=parcel_id,
                    address=address,
                    city=city or "Miami",
                    state="FL",
                    zip_code=zip_code or "",
                    property_type="residential",
                    record_type="foreclosure",
                    sale_price=price,
                    sale_date=sale_date,
                    seller=None,
                    buyer=None,
                    url=url
                ))

            except Exception as e:
                logger.warning(f"[{self.name}] Error parsing foreclosure: {e}")
                continue

        return results

    async def _get_cell_text(self, cells: list, index: int) -> Optional[str]:
        """Safely get text from a cell by index."""
        if index < len(cells):
            text = await cells[index].inner_text()
            return text.strip() if text else None
        return None

    def _parse_address_parts(self, address: str) -> tuple[Optional[str], Optional[str]]:
        """Extract city and zip from address."""
        city = None
        zip_code = None

        # Look for zip code
        zip_match = re.search(r"(\d{5})(-\d{4})?", address)
        if zip_match:
            zip_code = zip_match.group(1)

        # Look for Florida cities
        fl_cities = [
            "Miami", "Miami Beach", "Coral Gables", "Hialeah", "Homestead",
            "Doral", "Aventura", "Kendall", "Cutler Bay", "Pinecrest"
        ]
        for c in fl_cities:
            if c.lower() in address.lower():
                city = c
                break

        return city, zip_code

    def _generate_parcel_id(self, address: str) -> str:
        """Generate a pseudo parcel ID from address."""
        import hashlib
        return hashlib.md5(address.encode()).hexdigest()[:12]
