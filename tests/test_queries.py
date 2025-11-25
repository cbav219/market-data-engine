"""Unit tests for query engine module."""

import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path

from market_data_engine.queries import QueryEngine
from market_data_engine.sqlite_storage import SQLiteStorage
from market_data_engine.parquet_storage import ParquetStorage


class TestQueryEngine:
    """Tests for QueryEngine class."""
    
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
    
    @pytest.fixture
    def sqlite_storage(self, sample_df):
        """Create an in-memory SQLite storage with test data."""
        storage = SQLiteStorage(":memory:")
        storage.insert_data(sample_df)
        return storage
    
    @pytest.fixture
    def parquet_storage(self, tmp_path, sample_df):
        """Create a Parquet storage with test data."""
        storage = ParquetStorage(tmp_path / "parquet")
        storage.save_data(sample_df)
        return storage
    
    @pytest.fixture
    def query_engine(self, sqlite_storage, parquet_storage):
        """Create a QueryEngine with both storage backends."""
        return QueryEngine(sqlite_storage, parquet_storage)
    
    def test_price_range_sqlite(self, query_engine):
        """Test price range query using SQLite."""
        result = query_engine.get_price_range(
            'AAPL',
            datetime(2024, 1, 2),
            datetime(2024, 1, 3, 23, 59),
            source='sqlite'
        )
        
        assert len(result) == 4
        assert all(result['ticker'] == 'AAPL')
    
    def test_price_range_parquet(self, query_engine):
        """Test price range query using Parquet."""
        result = query_engine.get_price_range(
            'AAPL',
            datetime(2024, 1, 2),
            datetime(2024, 1, 3, 23, 59),
            source='parquet'
        )
        
        assert len(result) == 4
        assert all(result['ticker'] == 'AAPL')
    
    def test_avg_volume_sqlite(self, query_engine):
        """Test average volume query using SQLite."""
        avg_vol = query_engine.get_avg_volume('AAPL', source='sqlite')
        
        expected = (1000000 + 950000 + 1100000 + 980000 + 1050000) / 5
        assert abs(avg_vol - expected) < 0.01
    
    def test_avg_volume_parquet(self, query_engine):
        """Test average volume query using Parquet."""
        avg_vol = query_engine.get_avg_volume('AAPL', source='parquet')
        
        expected = (1000000 + 950000 + 1100000 + 980000 + 1050000) / 5
        assert abs(avg_vol - expected) < 0.01
    
    def test_weekly_returns_sqlite(self, query_engine):
        """Test weekly returns query using SQLite."""
        result = query_engine.get_weekly_returns('AAPL', source='sqlite')
        
        assert len(result) >= 1
        assert 'weekly_return' in result.columns
    
    def test_weekly_returns_parquet(self, query_engine):
        """Test weekly returns query using Parquet."""
        result = query_engine.get_weekly_returns('AAPL', source='parquet')
        
        assert len(result) >= 1
        assert 'weekly_return' in result.columns
    
    def test_daily_first_last_sqlite(self, query_engine):
        """Test daily first/last prices using SQLite."""
        result = query_engine.get_daily_first_last_prices('AAPL', source='sqlite')
        
        assert len(result) == 3
        assert 'first_price' in result.columns
        assert 'last_price' in result.columns
    
    def test_daily_first_last_parquet(self, query_engine):
        """Test daily first/last prices using Parquet."""
        result = query_engine.get_daily_first_last_prices('AAPL', source='parquet')
        
        assert len(result) == 3
        assert 'first_price' in result.columns
        assert 'last_price' in result.columns
    
    def test_volatility(self, query_engine):
        """Test volatility computation."""
        result = query_engine.get_volatility('AAPL', window=3)
        
        assert 'volatility' in result.columns
        assert len(result) == 5
    
    def test_compare_sources(self, query_engine):
        """Test comparison of SQLite and Parquet sources."""
        result = query_engine.compare_sources(
            'AAPL',
            datetime(2024, 1, 2),
            datetime(2024, 1, 4)
        )
        
        assert result['match'] is True
        assert result['sqlite']['record_count'] == result['parquet']['record_count']
    
    def test_invalid_source(self, query_engine):
        """Test error on invalid source."""
        with pytest.raises(ValueError, match="Invalid or unavailable source"):
            query_engine.get_price_range(
                'AAPL',
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
                source='invalid'
            )
    
    def test_sqlite_only_engine(self, sqlite_storage):
        """Test query engine with only SQLite backend."""
        engine = QueryEngine(sqlite_storage=sqlite_storage)
        
        result = engine.get_price_range(
            'AAPL',
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
            source='sqlite'
        )
        
        assert len(result) == 5
        
        with pytest.raises(ValueError):
            engine.get_price_range(
                'AAPL',
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
                source='parquet'
            )
    
    def test_parquet_only_engine(self, parquet_storage):
        """Test query engine with only Parquet backend."""
        engine = QueryEngine(parquet_storage=parquet_storage)
        
        result = engine.get_price_range(
            'AAPL',
            datetime(2024, 1, 1),
            datetime(2024, 1, 31),
            source='parquet'
        )
        
        assert len(result) == 5
        
        with pytest.raises(ValueError):
            engine.get_price_range(
                'AAPL',
                datetime(2024, 1, 1),
                datetime(2024, 1, 31),
                source='sqlite'
            )
