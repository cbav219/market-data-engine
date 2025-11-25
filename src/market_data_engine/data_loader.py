"""Data loading utilities for the market data engine."""

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .ingestion import CSVIngester
from .sqlite_storage import SQLiteStorage
from .parquet_storage import ParquetStorage


def load_and_validate(
    csv_path: str | Path = "market_data_multi.csv",
    tickers_path: str | Path = "tickers.csv",
) -> pd.DataFrame:
    """
    Load raw CSV data and validate against expected tickers.
    
    Args:
        csv_path: Path to the OHLCV CSV file.
        tickers_path: Path to the ticker metadata CSV file.
        
    Returns:
        Validated DataFrame.
    """
    tickers_df = pd.read_csv(tickers_path)
    expected_tickers = set(tickers_df['symbol'].astype(str).str.upper().str.strip())
    
    ingester = CSVIngester(expected_tickers=expected_tickers)
    df = ingester.load_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def build_sqlite_store(
    df: pd.DataFrame,
    db_path: str | Path = "market_data.db",
) -> Tuple[SQLiteStorage, int]:
    """
    Create a SQLite database and insert data.
    
    Args:
        df: Validated OHLCV DataFrame.
        db_path: Database path.
        
    Returns:
        Tuple of SQLiteStorage instance and number of rows inserted.
    """
    storage = SQLiteStorage(db_path)
    rows = storage.insert_data(df)
    return storage, rows


def build_parquet_store(
    df: pd.DataFrame,
    base_path: str | Path = "market_data",
    partition_by_ticker: bool = True,
) -> ParquetStorage:
    """
    Create Parquet storage and persist the dataset.
    
    Args:
        df: Validated OHLCV DataFrame.
        base_path: Root directory for Parquet files.
        partition_by_ticker: Whether to partition by ticker symbol.
        
    Returns:
        ParquetStorage instance.
    """
    storage = ParquetStorage(base_path)
    storage.save_data(df, partition_by_ticker=partition_by_ticker)
    return storage


def build_all_assets(
    csv_path: str | Path = "market_data_multi.csv",
    tickers_path: str | Path = "tickers.csv",
    sqlite_path: str | Path = "market_data.db",
    parquet_path: str | Path = "market_data",
) -> dict:
    """
    Convenience helper to build both SQLite and Parquet artifacts from a CSV.
    
    Returns:
        Dictionary with DataFrame, storage instances, and counts.
    """
    df = load_and_validate(csv_path, tickers_path)
    sqlite_storage, rows = build_sqlite_store(df, sqlite_path)
    parquet_storage = build_parquet_store(df, parquet_path)
    return {
        "dataframe": df,
        "rows_inserted": rows,
        "sqlite": sqlite_storage,
        "parquet": parquet_storage,
    }


if __name__ == "__main__":
    assets = build_all_assets()
    print(f"Loaded {len(assets['dataframe'])} rows")
    print(f"SQLite rows inserted: {assets['rows_inserted']}")
    print(f"SQLite DB: {Path('market_data.db').resolve()}")
    print(f"Parquet directory: {Path('market_data').resolve()}")
