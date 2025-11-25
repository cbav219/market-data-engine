"""Market Data Engine - A Python system for ingesting, storing, and querying multi-ticker market data."""

__version__ = "0.1.0"

from .ingestion import CSVIngester, ValidationError
from .sqlite_storage import SQLiteStorage
from .parquet_storage import ParquetStorage
from .queries import QueryEngine

__all__ = [
    "CSVIngester",
    "ValidationError",
    "SQLiteStorage",
    "ParquetStorage",
    "QueryEngine",
]
