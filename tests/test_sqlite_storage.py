"""Unit tests for SQLite storage module."""

import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path
import tempfile

from market_data_engine.sqlite_storage import SQLiteStorage


class TestSQLiteStorage:
    """Tests for SQLiteStorage class."""
    
    @pytest.fixture
    def storage(self):
        """Create an in-memory SQLite storage."""
        return SQLiteStorage(":memory:")
    
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
    
    def test_schema_creation(self, storage):
        """Test that database schema is created correctly."""
        tickers = storage.get_tickers()
        assert isinstance(tickers, list)
        # Initially empty
        assert len(tickers) == 0
    
    def test_insert_ticker(self, storage):
        """Test inserting a ticker."""
        ticker_id = storage.insert_ticker('AAPL', 'Apple Inc.')
        assert ticker_id == 1
        
        tickers = storage.get_tickers()
        assert len(tickers) == 1
        assert tickers[0]['symbol'] == 'AAPL'
        assert tickers[0]['name'] == 'Apple Inc.'
    
    def test_insert_ticker_duplicate(self, storage):
        """Test that duplicate ticker returns existing ID."""
        id1 = storage.insert_ticker('AAPL')
        id2 = storage.insert_ticker('AAPL')
        
        assert id1 == id2
        tickers = storage.get_tickers()
        assert len(tickers) == 1
    
    def test_insert_data(self, storage, sample_df):
        """Test inserting OHLCV data."""
        rows = storage.insert_data(sample_df)
        
        assert rows == 10
        tickers = storage.get_tickers()
        assert len(tickers) == 2
        assert set(t['symbol'] for t in tickers) == {'AAPL', 'GOOGL'}
    
    def test_get_price_range(self, storage, sample_df):
        """Test getting price data for a date range."""
        storage.insert_data(sample_df)
        
        start = datetime(2024, 1, 2, 0, 0)
        end = datetime(2024, 1, 3, 23, 59)
        
        result = storage.get_price_range('AAPL', start, end)
        
        assert len(result) == 4
        assert all(result['ticker'] == 'AAPL')
        assert result['timestamp'].min() >= start
        assert result['timestamp'].max() <= end
    
    def test_get_avg_volume(self, storage, sample_df):
        """Test calculating average volume."""
        storage.insert_data(sample_df)
        
        avg_vol = storage.get_avg_volume('AAPL')
        
        expected_avg = sum([1000000, 950000, 1100000, 980000, 1050000]) / 5
        assert abs(avg_vol - expected_avg) < 0.01
    
    def test_get_weekly_returns(self, storage, sample_df):
        """Test calculating weekly returns."""
        storage.insert_data(sample_df)
        
        result = storage.get_weekly_returns('AAPL')
        
        assert len(result) >= 1
        assert 'weekly_return' in result.columns
        assert 'first_open' in result.columns
        assert 'last_close' in result.columns
    
    def test_get_daily_first_last_prices(self, storage, sample_df):
        """Test getting daily first and last prices."""
        storage.insert_data(sample_df)
        
        result = storage.get_daily_first_last_prices('AAPL')
        
        # Should have 3 days of data
        assert len(result) == 3
        assert 'date' in result.columns
        assert 'first_price' in result.columns
        assert 'last_price' in result.columns
        assert 'first_timestamp' in result.columns
        assert 'last_timestamp' in result.columns
    
    def test_first_last_all_tickers(self, storage, sample_df):
        """First/last prices per day for all tickers."""
        storage.insert_data(sample_df)
        result = storage.get_first_last_prices_per_day()
        
        assert set(result['ticker'].unique()) == {'AAPL', 'GOOGL'}
        assert {'first_price', 'last_price', 'first_timestamp', 'last_timestamp'} <= set(result.columns)
    
    def test_avg_daily_volume(self, storage, sample_df):
        """Average daily volume per ticker aggregates per day first."""
        storage.insert_data(sample_df)
        result = storage.get_avg_daily_volume()
        
        assert set(result['ticker']) == {'AAPL', 'GOOGL'}
        assert 'avg_daily_volume' in result.columns
    
    def test_top_tickers_by_return(self, storage, sample_df):
        """Top tickers by return over window."""
        storage.insert_data(sample_df)
        start = datetime(2024, 1, 2)
        end = datetime(2024, 1, 4, 23, 59)
        result = storage.get_top_tickers_by_return(start, end, limit=2)
        
        assert len(result) == 2
        assert 'return_pct' in result.columns
    
    def test_file_based_storage(self, tmp_path, sample_df):
        """Test file-based SQLite storage."""
        db_path = tmp_path / "test.db"
        storage = SQLiteStorage(db_path)
        
        storage.insert_data(sample_df)
        storage.close()
        
        # Verify file exists
        assert db_path.exists()
        
        # Reopen and verify data
        storage2 = SQLiteStorage(db_path)
        tickers = storage2.get_tickers()
        assert len(tickers) == 2
        storage2.close()
    
    def test_empty_result(self, storage):
        """Test querying when no data exists."""
        result = storage.get_price_range(
            'AAPL',
            datetime(2024, 1, 1),
            datetime(2024, 1, 31)
        )
        assert len(result) == 0
        
        avg_vol = storage.get_avg_volume('AAPL')
        assert avg_vol == 0.0
    
    def test_multiple_inserts(self, storage, sample_df):
        """Test that multiple inserts of same data use REPLACE."""
        rows1 = storage.insert_data(sample_df)
        rows2 = storage.insert_data(sample_df)
        
        assert rows1 == 10
        assert rows2 == 10
        
        # Should still have same number of records (REPLACE behavior)
        result = storage.get_price_range(
            'AAPL',
            datetime(2024, 1, 1),
            datetime(2024, 12, 31)
        )
        assert len(result) == 5


class TestSQLiteSchema:
    """Tests for SQLite schema structure."""
    
    @pytest.fixture
    def storage(self):
        """Create an in-memory SQLite storage."""
        return SQLiteStorage(":memory:")
    
    def test_tickers_table_columns(self, storage):
        """Test tickers table has correct columns."""
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tickers)")
            columns = {row['name'] for row in cursor.fetchall()}
        
        assert 'ticker_id' in columns
        assert 'symbol' in columns
        assert 'name' in columns
        assert 'exchange' in columns
        assert 'created_at' in columns
    
    def test_prices_table_columns(self, storage):
        """Test prices table has correct columns."""
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(prices)")
            columns = {row['name'] for row in cursor.fetchall()}
        
        assert 'id' in columns
        assert 'ticker_id' in columns
        assert 'timestamp' in columns
        assert 'open' in columns
        assert 'high' in columns
        assert 'low' in columns
        assert 'close' in columns
        assert 'volume' in columns
    
    def test_indexes_exist(self, storage):
        """Test that indexes are created."""
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row['name'] for row in cursor.fetchall()}
        
        assert 'idx_prices_ticker_id' in indexes
        assert 'idx_prices_timestamp' in indexes
        assert 'idx_prices_ticker_timestamp' in indexes
    
    def test_foreign_key_constraint(self, storage):
        """Test that foreign key relationship exists in schema."""
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='prices'")
            row = cursor.fetchone()
            create_sql = row['sql']
        
        assert 'FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id)' in create_sql
