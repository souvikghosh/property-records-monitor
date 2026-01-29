#!/usr/bin/env python3
"""
Property Records Monitor - Main Entry Point

Monitors county property records for sales, foreclosures, and liens.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from src.config import DATABASE_PATH, SCREENSHOT_ON_NEW
from src.database import Database
from src.scrapers import SCRAPERS, get_scraper
from src.notifiers import notify_all

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/monitor.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


async def run_scraper(scraper_name: str, db: Database, dry_run: bool = False):
    """Run a single scraper and store results."""
    new_records = []

    scraper = get_scraper(scraper_name)

    async with scraper:
        logger.info(f"Fetching from {scraper.name}...")

        try:
            results = await scraper.fetch_all()

            for result in results:
                record = scraper.to_property_record(result)
                record_id, is_new = await db.add_record(record)

                if is_new:
                    logger.info(
                        f"NEW: {record.address} | {record.formatted_price} | {record.record_type}"
                    )
                    record.id = record_id
                    new_records.append(record)

                    # Screenshot if enabled
                    if SCREENSHOT_ON_NEW and not dry_run and result.url:
                        try:
                            page = await scraper.new_page()
                            await page.goto(result.url, wait_until="domcontentloaded", timeout=20000)
                            await scraper.screenshot(page, record.parcel_id[:12])
                            await page.close()
                        except Exception as e:
                            logger.warning(f"Screenshot failed: {e}")

        except Exception as e:
            logger.error(f"Error with {scraper.name}: {e}")

    return new_records


async def main(sources: list[str] | None = None, dry_run: bool = False):
    """Main entry point."""
    logger.info("=" * 60)
    logger.info(f"Property Records Monitor - {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Determine which scrapers to run
    if sources:
        scrapers_to_run = [s for s in sources if s in SCRAPERS]
        if not scrapers_to_run:
            logger.error(f"No valid sources. Available: {list(SCRAPERS.keys())}")
            return 1
    else:
        # Default: run redfin_miami for demo
        scrapers_to_run = ["redfin_miami"]

    logger.info(f"Sources: {scrapers_to_run}")

    # Initialize database
    db = Database(DATABASE_PATH)
    await db.connect()

    try:
        all_new_records = []

        for scraper_name in scrapers_to_run:
            logger.info(f"\n--- {scraper_name} ---")
            new_records = await run_scraper(scraper_name, db, dry_run)
            all_new_records.extend(new_records)

        # Report
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Found {len(all_new_records)} new properties")

        if all_new_records:
            # Group by type
            sales = [r for r in all_new_records if r.record_type == "sale"]
            foreclosures = [r for r in all_new_records if r.record_type == "foreclosure"]

            if sales:
                logger.info(f"\nSales ({len(sales)}):")
                for r in sales[:10]:
                    logger.info(f"  {r.formatted_price} - {r.address}")

            if foreclosures:
                logger.info(f"\nForeclosures ({len(foreclosures)}):")
                for r in foreclosures[:10]:
                    logger.info(f"  {r.formatted_price} - {r.address}")

            # Notify
            if not dry_run:
                logger.info("\nSending notifications...")
                results = await notify_all(all_new_records)
                for notifier, success in results.items():
                    logger.info(f"  {notifier}: {'sent' if success else 'failed'}")

                # Mark notified
                for record in all_new_records:
                    if record.id:
                        await db.mark_notified(record.id)
            else:
                logger.info("\n[DRY RUN] Skipping notifications")

        # Stats
        stats = await db.get_stats()
        logger.info(f"\nDatabase: {stats['total_records']} total records")
        if stats['by_type']:
            logger.info(f"  By type: {stats['by_type']}")

        logger.info(f"\n{'=' * 60}")
        return 0

    finally:
        await db.close()


def cli():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Monitor property records for sales and foreclosures"
    )
    parser.add_argument(
        "--source", "-s",
        action="append",
        choices=list(SCRAPERS.keys()),
        help="Source(s) to search (can repeat). Default: redfin_miami"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Don't send notifications"
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="List available sources"
    )

    args = parser.parse_args()

    if args.list_sources:
        print("Available sources:")
        for name in SCRAPERS.keys():
            print(f"  - {name}")
        return 0

    return asyncio.run(main(sources=args.source, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(cli())
