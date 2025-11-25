"""CSV data ingestion module with validation for OHLCV market data."""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

import pandas as pd


class ValidationError(Exception):
    """Exception raised when data validation fails."""
    pass


@dataclass
class OHLCVRecord:
    """Represents a single OHLCV data record."""
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class CSVIngester:
    """Ingests and validates OHLCV data from CSV files."""
    
    REQUIRED_COLUMNS = {'ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume'}
    
    def __init__(
        self,
        expected_tickers: Optional[Set[str]] = None,
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
        min_price: float = 0.0,
        max_price: float = 1_000_000.0,
    ):
        """
        Initialize the CSV ingester.
        
        Args:
            expected_tickers: Set of expected ticker symbols for completeness check.
            timestamp_format: Format string for parsing timestamps.
            min_price: Minimum valid price (must be >= 0).
            max_price: Maximum valid price for validation.
        """
        self.expected_tickers = expected_tickers or set()
        self.timestamp_format = timestamp_format
        self.min_price = min_price
        self.max_price = max_price
        self.validation_errors: List[str] = []
    
    def load_csv(self, filepath: str | Path) -> pd.DataFrame:
        """
        Load and validate a CSV file containing OHLCV data.
        
        Args:
            filepath: Path to the CSV file.
            
        Returns:
            Validated DataFrame with OHLCV data.
            
        Raises:
            ValidationError: If validation fails.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise ValidationError(f"File not found: {filepath}")
        
        try:
            df = pd.read_csv(filepath)
        except Exception as e:
            raise ValidationError(f"Failed to read CSV file: {e}")
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Validate and transform data
        self._validate_columns(df)
        df = self._parse_timestamps(df)
        self._validate_prices(df)
        self._validate_volume(df)
        self._validate_ticker_completeness(df)
        
        return df
    
    def _validate_columns(self, df: pd.DataFrame) -> None:
        """Validate that all required columns are present."""
        missing_columns = self.REQUIRED_COLUMNS - set(df.columns)
        if missing_columns:
            raise ValidationError(f"Missing required columns: {missing_columns}")
    
    def _parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse and validate timestamps."""
        try:
            df['timestamp'] = pd.to_datetime(df['timestamp'], format=self.timestamp_format)
        except ValueError:
            # Try with automatic parsing
            try:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            except Exception as e:
                raise ValidationError(f"Failed to parse timestamps: {e}")
        
        # Check for null timestamps
        null_timestamps = df['timestamp'].isnull().sum()
        if null_timestamps > 0:
            raise ValidationError(f"Found {null_timestamps} records with invalid timestamps")
        
        # Check for duplicates (same ticker + timestamp)
        duplicates = df.duplicated(subset=['ticker', 'timestamp'], keep=False)
        if duplicates.any():
            dup_count = duplicates.sum()
            raise ValidationError(
                f"Found {dup_count} duplicate records (same ticker and timestamp)"
            )
        
        return df
    
    def _validate_prices(self, df: pd.DataFrame) -> None:
        """Validate price fields (open, high, low, close)."""
        price_columns = ['open', 'high', 'low', 'close']
        
        for col in price_columns:
            # Convert to numeric, coercing errors
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Check for null values
            null_count = df[col].isnull().sum()
            if null_count > 0:
                raise ValidationError(f"Found {null_count} invalid {col} prices")
            
            # Check price range
            out_of_range = (df[col] < self.min_price) | (df[col] > self.max_price)
            if out_of_range.any():
                invalid_count = out_of_range.sum()
                raise ValidationError(
                    f"Found {invalid_count} {col} prices out of valid range "
                    f"[{self.min_price}, {self.max_price}]"
                )
        
        # Validate OHLC consistency: low <= open, close <= high
        invalid_ohlc = (df['low'] > df['high']) | (df['low'] > df['open']) | \
                       (df['low'] > df['close']) | (df['high'] < df['open']) | \
                       (df['high'] < df['close'])
        if invalid_ohlc.any():
            invalid_count = invalid_ohlc.sum()
            raise ValidationError(
                f"Found {invalid_count} records with invalid OHLC relationship "
                "(high must be >= low, open, close)"
            )
    
    def _validate_volume(self, df: pd.DataFrame) -> None:
        """Validate volume field."""
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        # Check for null values
        null_count = df['volume'].isnull().sum()
        if null_count > 0:
            raise ValidationError(f"Found {null_count} invalid volume values")
        
        # Volume must be non-negative
        negative_volume = df['volume'] < 0
        if negative_volume.any():
            raise ValidationError(
                f"Found {negative_volume.sum()} records with negative volume"
            )
        
        # Convert to integer
        df['volume'] = df['volume'].astype('int64')
    
    def _validate_ticker_completeness(self, df: pd.DataFrame) -> None:
        """Validate that all expected tickers are present."""
        if not self.expected_tickers:
            return
        
        actual_tickers = set(df['ticker'].unique())
        missing_tickers = self.expected_tickers - actual_tickers
        
        if missing_tickers:
            raise ValidationError(
                f"Missing expected tickers: {missing_tickers}"
            )
    
    def to_records(self, df: pd.DataFrame) -> List[OHLCVRecord]:
        """Convert DataFrame to list of OHLCVRecord objects."""
        records = []
        for _, row in df.iterrows():
            record = OHLCVRecord(
                ticker=row['ticker'],
                timestamp=row['timestamp'].to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']),
            )
            records.append(record)
        return records
