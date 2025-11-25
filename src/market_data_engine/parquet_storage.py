"""Parquet storage module for OHLCV market data."""

import time
from pathlib import Path
from typing import Optional, List, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class ParquetStorage:
    """Parquet-based storage for OHLCV market data with ticker partitions."""
    
    def __init__(self, base_path: str | Path):
        """
        Initialize the Parquet storage.
        
        Args:
            base_path: Base directory for storing Parquet files.
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def save_data(
        self,
        df: pd.DataFrame,
        partition_by_ticker: bool = True,
    ) -> str:
        """
        Save OHLCV data to Parquet format.
        
        Args:
            df: DataFrame with OHLCV data.
            partition_by_ticker: Whether to partition by ticker symbol.
            
        Returns:
            Path where data was saved.
        """
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df = df.copy()
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Convert to PyArrow Table
        table = pa.Table.from_pandas(df)
        
        if partition_by_ticker:
            # Write with partitioning by ticker
            pq.write_to_dataset(
                table,
                root_path=str(self.base_path),
                partition_cols=['ticker'],
                existing_data_behavior='overwrite_or_ignore',
            )
        else:
            # Write as single file
            output_path = self.base_path / "data.parquet"
            pq.write_table(table, output_path)
        
        return str(self.base_path)
    
    def load_data(self, ticker: Optional[str] = None) -> pd.DataFrame:
        """
        Load OHLCV data from Parquet storage.
        
        Args:
            ticker: Optional ticker to filter by.
            
        Returns:
            DataFrame with OHLCV data.
        """
        if ticker:
            # Load specific ticker partition
            ticker_path = self.base_path / f"ticker={ticker}"
            if not ticker_path.exists():
                return pd.DataFrame()
            df = pq.read_table(ticker_path).to_pandas()
            df['ticker'] = ticker
        else:
            # Load all data
            if not any(self.base_path.iterdir()):
                return pd.DataFrame()
            df = pq.read_table(self.base_path).to_pandas()
        
        return df
    
    def get_date_range(
        self,
        ticker: str,
        start_date: str | pd.Timestamp,
        end_date: str | pd.Timestamp,
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a ticker within a date range.
        
        Args:
            ticker: Ticker symbol.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            
        Returns:
            DataFrame with filtered OHLCV data.
        """
        df = self.load_data(ticker)
        
        if df.empty:
            return df
        
        # Convert to timestamps for comparison
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date)
        
        # Ensure timestamp column is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Filter by date range
        mask = (df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)
        return df[mask].sort_values('timestamp').reset_index(drop=True)
    
    def compute_volatility(
        self,
        ticker: str,
        window: int = 5,
    ) -> pd.DataFrame:
        """
        Compute rolling volatility (standard deviation of returns) for a ticker.
        
        Args:
            ticker: Ticker symbol.
            window: Rolling window size in days.
            
        Returns:
            DataFrame with date and volatility columns.
        """
        df = self.load_data(ticker)
        
        if df.empty or len(df) < 2:
            return pd.DataFrame(columns=['timestamp', 'close', 'daily_return', 'volatility'])
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Calculate daily returns
        df['daily_return'] = df['close'].pct_change()
        
        # Calculate rolling volatility (standard deviation of returns)
        df['volatility'] = df['daily_return'].rolling(window=window).std()
        
        return df[['timestamp', 'close', 'daily_return', 'volatility']]
    
    def verify_integrity(self) -> dict:
        """
        Verify integrity of Parquet data.
        
        Returns:
            Dictionary with integrity check results.
        """
        results = {
            'valid': True,
            'errors': [],
            'tickers': [],
            'total_records': 0,
            'partitions': [],
        }
        
        try:
            # Check for partitions
            for partition_dir in self.base_path.iterdir():
                if partition_dir.is_dir() and partition_dir.name.startswith('ticker='):
                    ticker = partition_dir.name.split('=')[1]
                    results['partitions'].append(ticker)
                    results['tickers'].append(ticker)
                    
                    # Try to read the partition
                    try:
                        table = pq.read_table(partition_dir)
                        results['total_records'] += table.num_rows
                    except Exception as e:
                        results['valid'] = False
                        results['errors'].append(f"Error reading {ticker}: {e}")
            
            # If no partitions, try reading as single file
            if not results['partitions']:
                single_file = self.base_path / "data.parquet"
                if single_file.exists():
                    try:
                        table = pq.read_table(single_file)
                        results['total_records'] = table.num_rows
                        if 'ticker' in table.column_names:
                            results['tickers'] = table['ticker'].to_pylist()
                            results['tickers'] = list(set(results['tickers']))
                    except Exception as e:
                        results['valid'] = False
                        results['errors'].append(f"Error reading data.parquet: {e}")
        
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f"Integrity check failed: {e}")
        
        return results


def benchmark_parquet_vs_sqlite(
    df: pd.DataFrame,
    sqlite_storage,
    parquet_storage: ParquetStorage,
    ticker: str,
    iterations: int = 10,
) -> dict:
    """
    Benchmark Parquet vs SQLite query performance.
    
    Args:
        df: DataFrame with test data.
        sqlite_storage: SQLiteStorage instance.
        parquet_storage: ParquetStorage instance.
        ticker: Ticker to query.
        iterations: Number of iterations for timing.
        
    Returns:
        Dictionary with benchmark results.
    """
    from datetime import datetime, timedelta
    
    results = {
        'sqlite': {},
        'parquet': {},
    }
    
    # Get date range from data
    start_date = df['timestamp'].min()
    end_date = df['timestamp'].max()
    
    # Benchmark date range query
    # SQLite
    sqlite_times = []
    for _ in range(iterations):
        start = time.time()
        sqlite_storage.get_price_range(ticker, start_date, end_date)
        sqlite_times.append(time.time() - start)
    results['sqlite']['date_range_query'] = {
        'avg_time': sum(sqlite_times) / len(sqlite_times),
        'min_time': min(sqlite_times),
        'max_time': max(sqlite_times),
    }
    
    # Parquet
    parquet_times = []
    for _ in range(iterations):
        start = time.time()
        parquet_storage.get_date_range(ticker, start_date, end_date)
        parquet_times.append(time.time() - start)
    results['parquet']['date_range_query'] = {
        'avg_time': sum(parquet_times) / len(parquet_times),
        'min_time': min(parquet_times),
        'max_time': max(parquet_times),
    }
    
    # Benchmark full data load
    # SQLite
    sqlite_times = []
    for _ in range(iterations):
        start = time.time()
        sqlite_storage.get_price_range(ticker, start_date, end_date)
        sqlite_times.append(time.time() - start)
    results['sqlite']['full_load'] = {
        'avg_time': sum(sqlite_times) / len(sqlite_times),
    }
    
    # Parquet
    parquet_times = []
    for _ in range(iterations):
        start = time.time()
        parquet_storage.load_data(ticker)
        parquet_times.append(time.time() - start)
    results['parquet']['full_load'] = {
        'avg_time': sum(parquet_times) / len(parquet_times),
    }
    
    # Benchmark volatility computation
    parquet_vol_times = []
    for _ in range(iterations):
        start = time.time()
        parquet_storage.compute_volatility(ticker, window=5)
        parquet_vol_times.append(time.time() - start)
    results['parquet']['volatility_computation'] = {
        'avg_time': sum(parquet_vol_times) / len(parquet_vol_times),
    }
    
    return results
