"""Market Data Engine - A Python system for ingesting, storing, and querying multi-ticker market data."""

__version__ = "0.1.0"

from .ingestion import CSVIngester, ValidationError
from .sqlite_storage import SQLiteStorage
from .parquet_storage import ParquetStorage
from .queries import QueryEngine
from .data_loader import (
    load_and_validate,
    build_sqlite_store,
    build_parquet_store,
    build_all_assets,
)

__all__ = [
    "CSVIngester",
    "ValidationError",
    "SQLiteStorage",
    "ParquetStorage",
    "QueryEngine",
    "load_and_validate",
    "build_sqlite_store",
    "build_parquet_store",
    "build_all_assets",
]
