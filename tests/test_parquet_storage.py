"""Unit tests for Parquet storage module."""

import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path
import shutil

from market_data_engine.parquet_storage import ParquetStorage, benchmark_parquet_vs_sqlite
from market_data_engine.sqlite_storage import SQLiteStorage


class TestParquetStorage:
    """Tests for ParquetStorage class."""
    
    @pytest.fixture
    def parquet_dir(self, tmp_path):
        """Create a temporary directory for Parquet files."""
        parquet_path = tmp_path / "parquet_data"
        parquet_path.mkdir()
        return parquet_path
    
    @pytest.fixture
    def storage(self, parquet_dir):
        """Create a ParquetStorage instance."""
        return ParquetStorage(parquet_dir)
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame for testing."""
        data = {
            'ticker': ['AAPL'] * 5 + ['GOOGL'] * 5,
            'timestamp': [
                datetime(2024, 1, 2, 9, 30),
                datetime(2024, 1, 2, 10, 0),
                datetime(2024, 1, 3, 9, 30),
                datetime(2024, 1, 3, 10, 0),
                datetime(2024, 1, 4, 9, 30),
                datetime(2024, 1, 2, 9, 30),
                datetime(2024, 1, 2, 10, 0),
                datetime(2024, 1, 3, 9, 30),
                datetime(2024, 1, 3, 10, 0),
                datetime(2024, 1, 4, 9, 30),
            ],
            'open': [185.50, 185.75, 186.25, 186.75, 187.25, 140.00, 140.25, 140.75, 141.00, 141.50],
            'high': [186.00, 186.25, 187.00, 187.25, 188.00, 140.50, 140.75, 141.25, 141.50, 142.00],
            'low': [185.00, 185.50, 186.00, 186.50, 187.00, 139.50, 140.00, 140.50, 140.75, 141.25],
            'close': [185.75, 186.00, 186.75, 187.00, 187.75, 140.25, 140.50, 141.00, 141.25, 141.75],
            'volume': [1000000, 950000, 1100000, 980000, 1050000, 800000, 750000, 850000, 780000, 830000],
        }
        return pd.DataFrame(data)
    
    def test_save_with_partitions(self, storage, sample_df):
        """Test saving data with ticker partitions."""
        path = storage.save_data(sample_df, partition_by_ticker=True)
        
        assert Path(path).exists()
        # Check partitions were created
        assert (storage.base_path / "ticker=AAPL").exists()
        assert (storage.base_path / "ticker=GOOGL").exists()
    
    def test_save_without_partitions(self, storage, sample_df):
        """Test saving data without partitions."""
        path = storage.save_data(sample_df, partition_by_ticker=False)
        
        assert Path(path).exists()
        assert (storage.base_path / "data.parquet").exists()
    
    def test_load_all_data(self, storage, sample_df):
        """Test loading all data."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.load_data()
        
        assert len(result) == 10
        assert set(result['ticker'].unique()) == {'AAPL', 'GOOGL'}
    
    def test_load_single_ticker(self, storage, sample_df):
        """Test loading data for a single ticker."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.load_data(ticker='AAPL')
        
        assert len(result) == 5
        assert all(result['ticker'] == 'AAPL')
    
    def test_get_date_range(self, storage, sample_df):
        """Test getting data for a date range."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.get_date_range(
            'AAPL',
            '2024-01-02',
            '2024-01-03 23:59:59'
        )
        
        assert len(result) == 4
        assert all(result['ticker'] == 'AAPL')
    
    def test_compute_volatility(self, storage, sample_df):
        """Test computing 5-day rolling volatility."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.compute_volatility('AAPL', window=5)
        
        assert 'volatility' in result.columns
        assert 'daily_return' in result.columns
        assert len(result) == 5
        # First N-1 values should be NaN for N-day window
        assert pd.isna(result['volatility'].iloc[0])
    
    def test_verify_integrity_valid(self, storage, sample_df):
        """Test integrity verification on valid data."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.verify_integrity()
        
        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert result['total_records'] == 10
        assert set(result['tickers']) == {'AAPL', 'GOOGL'}
    
    def test_verify_integrity_empty(self, parquet_dir):
        """Test integrity verification on empty storage."""
        storage = ParquetStorage(parquet_dir)
        
        result = storage.verify_integrity()
        
        assert result['valid'] is True
        assert result['total_records'] == 0
    
    def test_load_nonexistent_ticker(self, storage, sample_df):
        """Test loading a ticker that doesn't exist."""
        storage.save_data(sample_df, partition_by_ticker=True)
        
        result = storage.load_data(ticker='MSFT')
        
        assert len(result) == 0


class TestParquetIntegrity:
    """Tests for Parquet data integrity."""
    
    @pytest.fixture
    def parquet_dir(self, tmp_path):
        """Create a temporary directory for Parquet files."""
        parquet_path = tmp_path / "parquet_data"
        parquet_path.mkdir()
        return parquet_path
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame."""
        data = {
            'ticker': ['AAPL'] * 3,
            'timestamp': [
                datetime(2024, 1, 2, 9, 30),
                datetime(2024, 1, 2, 10, 0),
                datetime(2024, 1, 3, 9, 30),
            ],
            'open': [185.50, 185.75, 186.25],
            'high': [186.00, 186.25, 187.00],
            'low': [185.00, 185.50, 186.00],
            'close': [185.75, 186.00, 186.75],
            'volume': [1000000, 950000, 1100000],
        }
        return pd.DataFrame(data)
    
    def test_data_round_trip(self, parquet_dir, sample_df):
        """Test that data survives save/load cycle."""
        storage = ParquetStorage(parquet_dir)
        storage.save_data(sample_df, partition_by_ticker=True)
        
        loaded = storage.load_data(ticker='AAPL')
        
        # Sort both for comparison
        sample_sorted = sample_df.sort_values('timestamp').reset_index(drop=True)
        loaded_sorted = loaded.sort_values('timestamp').reset_index(drop=True)
        
        assert len(loaded_sorted) == len(sample_sorted)
        assert list(loaded_sorted['open']) == list(sample_sorted['open'])
        assert list(loaded_sorted['volume']) == list(sample_sorted['volume'])
    
    def test_column_types_preserved(self, parquet_dir, sample_df):
        """Test that column types are preserved."""
        storage = ParquetStorage(parquet_dir)
        storage.save_data(sample_df, partition_by_ticker=True)
        
        loaded = storage.load_data(ticker='AAPL')
        
        assert loaded['open'].dtype == 'float64'
        assert loaded['volume'].dtype == 'int64'
    
    def test_partitions_independent(self, parquet_dir, sample_df):
        """Test that partitions are independent."""
        # Add GOOGL data
        googl_data = sample_df.copy()
        googl_data['ticker'] = 'GOOGL'
        googl_data['open'] = googl_data['open'] - 40  # Different prices
        
        combined = pd.concat([sample_df, googl_data], ignore_index=True)
        
        storage = ParquetStorage(parquet_dir)
        storage.save_data(combined, partition_by_ticker=True)
        
        aapl = storage.load_data(ticker='AAPL')
        googl = storage.load_data(ticker='GOOGL')
        
        assert len(aapl) == 3
        assert len(googl) == 3
        assert aapl['open'].iloc[0] != googl['open'].iloc[0]


class TestBenchmark:
    """Tests for benchmark functionality."""
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame."""
        data = {
            'ticker': ['AAPL'] * 10,
            'timestamp': [datetime(2024, 1, i+1, 9, 30) for i in range(10)],
            'open': [185.50 + i for i in range(10)],
            'high': [186.00 + i for i in range(10)],
            'low': [185.00 + i for i in range(10)],
            'close': [185.75 + i for i in range(10)],
            'volume': [1000000 + i*10000 for i in range(10)],
        }
        return pd.DataFrame(data)
    
    def test_benchmark_runs(self, tmp_path, sample_df):
        """Test that benchmark function executes."""
        sqlite_storage = SQLiteStorage(":memory:")
        sqlite_storage.insert_data(sample_df)
        
        parquet_dir = tmp_path / "parquet"
        parquet_storage = ParquetStorage(parquet_dir)
        parquet_storage.save_data(sample_df)
        
        results = benchmark_parquet_vs_sqlite(
            sample_df,
            sqlite_storage,
            parquet_storage,
            ticker='AAPL',
            iterations=2,
        )
        
        assert 'sqlite' in results
        assert 'parquet' in results
        assert 'date_range_query' in results['sqlite']
        assert 'date_range_query' in results['parquet']
        assert 'volatility_computation' in results['parquet']
