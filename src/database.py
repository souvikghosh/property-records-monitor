import aiosqlite
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


@dataclass
class PropertyRecord:
    """Represents a property record entry."""
    id: Optional[int]
    county: str
    parcel_id: str  # Unique parcel/folio number
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
    raw_data: Optional[str]  # JSON of extra fields
    first_seen: datetime
    last_seen: datetime
    notified: bool = False

    @property
    def unique_key(self) -> str:
        """Unique identifier for deduplication."""
        return f"{self.county}:{self.parcel_id}:{self.record_type}:{self.sale_date or 'na'}"

    @property
    def formatted_price(self) -> str:
        """Format price for display."""
        if self.sale_price:
            return f"${self.sale_price:,}"
        return "N/A"


class Database:
    """Async SQLite database for tracking property records."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open database connection and create tables."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                county TEXT NOT NULL,
                parcel_id TEXT NOT NULL,
                address TEXT NOT NULL,
                city TEXT,
                state TEXT,
                zip_code TEXT,
                property_type TEXT,
                record_type TEXT NOT NULL,
                sale_price INTEGER,
                sale_date TEXT,
                seller TEXT,
                buyer TEXT,
                url TEXT NOT NULL,
                raw_data TEXT,
                first_seen TIMESTAMP NOT NULL,
                last_seen TIMESTAMP NOT NULL,
                notified INTEGER DEFAULT 0,
                UNIQUE(county, parcel_id, record_type, sale_date)
            )
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_properties_county
            ON properties(county)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_properties_zip
            ON properties(zip_code)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_properties_type
            ON properties(record_type)
        """)

        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_properties_price
            ON properties(sale_price)
        """)

        await self._connection.commit()

    async def record_exists(self, county: str, parcel_id: str, record_type: str, sale_date: str = None) -> bool:
        """Check if a record already exists."""
        cursor = await self._connection.execute(
            """SELECT 1 FROM properties
               WHERE county = ? AND parcel_id = ? AND record_type = ?
               AND (sale_date = ? OR (sale_date IS NULL AND ? IS NULL))""",
            (county, parcel_id, record_type, sale_date, sale_date)
        )
        row = await cursor.fetchone()
        return row is not None

    async def add_record(self, record: PropertyRecord) -> tuple[int, bool]:
        """
        Add or update a property record.

        Returns:
            Tuple of (record_id, is_new)
        """
        now = datetime.utcnow()

        # Check if exists
        cursor = await self._connection.execute(
            """SELECT id FROM properties
               WHERE county = ? AND parcel_id = ? AND record_type = ?
               AND (sale_date = ? OR (sale_date IS NULL AND ? IS NULL))""",
            (record.county, record.parcel_id, record.record_type,
             record.sale_date, record.sale_date)
        )
        existing = await cursor.fetchone()

        if existing:
            # Update last_seen
            await self._connection.execute(
                "UPDATE properties SET last_seen = ? WHERE id = ?",
                (now, existing["id"])
            )
            await self._connection.commit()
            return existing["id"], False

        # Insert new record
        cursor = await self._connection.execute(
            """
            INSERT INTO properties
            (county, parcel_id, address, city, state, zip_code, property_type,
             record_type, sale_price, sale_date, seller, buyer, url, raw_data,
             first_seen, last_seen, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.county,
                record.parcel_id,
                record.address,
                record.city,
                record.state,
                record.zip_code,
                record.property_type,
                record.record_type,
                record.sale_price,
                record.sale_date,
                record.seller,
                record.buyer,
                record.url,
                record.raw_data,
                now,
                now,
                0
            )
        )
        await self._connection.commit()
        return cursor.lastrowid, True

    async def mark_notified(self, record_id: int) -> None:
        """Mark a record as notified."""
        await self._connection.execute(
            "UPDATE properties SET notified = 1 WHERE id = ?",
            (record_id,)
        )
        await self._connection.commit()

    async def get_unnotified_records(self) -> list[PropertyRecord]:
        """Get all records that haven't been notified yet."""
        cursor = await self._connection.execute(
            "SELECT * FROM properties WHERE notified = 0 ORDER BY first_seen DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_records_by_county(self, county: str, limit: int = 50) -> list[PropertyRecord]:
        """Get records for a specific county."""
        cursor = await self._connection.execute(
            "SELECT * FROM properties WHERE county = ? ORDER BY first_seen DESC LIMIT ?",
            (county, limit)
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_foreclosures(self, limit: int = 50) -> list[PropertyRecord]:
        """Get recent foreclosure records."""
        cursor = await self._connection.execute(
            "SELECT * FROM properties WHERE record_type = 'foreclosure' ORDER BY first_seen DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = await self._connection.execute(
            "SELECT COUNT(*) as total, SUM(notified) as notified FROM properties"
        )
        row = await cursor.fetchone()

        cursor = await self._connection.execute(
            "SELECT county, COUNT(*) as count FROM properties GROUP BY county"
        )
        by_county = {r["county"]: r["count"] for r in await cursor.fetchall()}

        cursor = await self._connection.execute(
            "SELECT record_type, COUNT(*) as count FROM properties GROUP BY record_type"
        )
        by_type = {r["record_type"]: r["count"] for r in await cursor.fetchall()}

        return {
            "total_records": row["total"] or 0,
            "notified": row["notified"] or 0,
            "by_county": by_county,
            "by_type": by_type
        }

    def _row_to_record(self, row: aiosqlite.Row) -> PropertyRecord:
        """Convert database row to PropertyRecord."""
        return PropertyRecord(
            id=row["id"],
            county=row["county"],
            parcel_id=row["parcel_id"],
            address=row["address"],
            city=row["city"],
            state=row["state"],
            zip_code=row["zip_code"],
            property_type=row["property_type"],
            record_type=row["record_type"],
            sale_price=row["sale_price"],
            sale_date=row["sale_date"],
            seller=row["seller"],
            buyer=row["buyer"],
            url=row["url"],
            raw_data=row["raw_data"],
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_seen=datetime.fromisoformat(row["last_seen"]),
            notified=bool(row["notified"])
        )
