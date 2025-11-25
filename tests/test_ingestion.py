"""Unit tests for CSV ingestion module."""

import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path
import tempfile
import os

from market_data_engine.ingestion import CSVIngester, ValidationError, OHLCVRecord


class TestCSVIngester:
    """Tests for CSVIngester class."""
    
    @pytest.fixture
    def sample_csv(self, tmp_path):
        """Create a sample CSV file for testing."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,1000000
AAPL,2024-01-02 10:00:00,185.75,186.25,185.50,186.00,950000
GOOGL,2024-01-02 09:30:00,140.00,140.50,139.50,140.25,800000
GOOGL,2024-01-02 10:00:00,140.25,140.75,140.00,140.50,750000
"""
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text(csv_content)
        return csv_file
    
    @pytest.fixture
    def ingester(self):
        """Create a CSVIngester instance."""
        return CSVIngester()
    
    def test_load_valid_csv(self, ingester, sample_csv):
        """Test loading a valid CSV file."""
        df = ingester.load_csv(sample_csv)
        
        assert len(df) == 4
        assert set(df['ticker'].unique()) == {'AAPL', 'GOOGL'}
        assert 'timestamp' in df.columns
        assert 'open' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns
    
    def test_file_not_found(self, ingester):
        """Test error when file doesn't exist."""
        with pytest.raises(ValidationError, match="File not found"):
            ingester.load_csv("/nonexistent/file.csv")
    
    def test_missing_columns(self, ingester, tmp_path):
        """Test error when required columns are missing."""
        csv_content = """ticker,timestamp,open,high,low
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00
"""
        csv_file = tmp_path / "missing_cols.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="Missing required columns"):
            ingester.load_csv(csv_file)
    
    def test_invalid_timestamps(self, ingester, tmp_path):
        """Test error when timestamps are invalid."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,invalid_date,185.50,186.00,185.00,185.75,1000000
"""
        csv_file = tmp_path / "invalid_ts.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="parse timestamps"):
            ingester.load_csv(csv_file)
    
    def test_invalid_prices_negative(self, ingester, tmp_path):
        """Test error when prices are negative."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,-185.50,186.00,185.00,185.75,1000000
"""
        csv_file = tmp_path / "negative_price.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="out of valid range"):
            ingester.load_csv(csv_file)
    
    def test_invalid_ohlc_relationship(self, ingester, tmp_path):
        """Test error when OHLC values are inconsistent."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,180.00,185.00,185.75,1000000
"""
        csv_file = tmp_path / "invalid_ohlc.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="invalid OHLC relationship"):
            ingester.load_csv(csv_file)
    
    def test_negative_volume(self, ingester, tmp_path):
        """Test error when volume is negative."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,-1000000
"""
        csv_file = tmp_path / "negative_vol.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="negative volume"):
            ingester.load_csv(csv_file)
    
    def test_duplicate_records(self, ingester, tmp_path):
        """Test error when duplicate records exist."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,1000000
AAPL,2024-01-02 09:30:00,185.60,186.10,185.10,185.85,1001000
"""
        csv_file = tmp_path / "duplicate.csv"
        csv_file.write_text(csv_content)
        
        with pytest.raises(ValidationError, match="duplicate records"):
            ingester.load_csv(csv_file)
    
    def test_ticker_completeness_check(self, tmp_path):
        """Test ticker completeness validation."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,1000000
"""
        csv_file = tmp_path / "incomplete.csv"
        csv_file.write_text(csv_content)
        
        ingester = CSVIngester(expected_tickers={'AAPL', 'GOOGL'})
        
        with pytest.raises(ValidationError, match="Missing expected tickers"):
            ingester.load_csv(csv_file)
    
    def test_ticker_completeness_passes(self, tmp_path):
        """Test ticker completeness passes when all tickers present."""
        csv_content = """ticker,timestamp,open,high,low,close,volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,1000000
GOOGL,2024-01-02 09:30:00,140.00,140.50,139.50,140.25,800000
"""
        csv_file = tmp_path / "complete.csv"
        csv_file.write_text(csv_content)
        
        ingester = CSVIngester(expected_tickers={'AAPL', 'GOOGL'})
        df = ingester.load_csv(csv_file)
        
        assert len(df) == 2
    
    def test_to_records(self, ingester, sample_csv):
        """Test conversion of DataFrame to OHLCVRecord objects."""
        df = ingester.load_csv(sample_csv)
        records = ingester.to_records(df)
        
        assert len(records) == 4
        assert all(isinstance(r, OHLCVRecord) for r in records)
        assert records[0].ticker == 'AAPL'
        assert isinstance(records[0].timestamp, datetime)
        assert isinstance(records[0].open, float)
        assert isinstance(records[0].volume, int)
    
    def test_column_name_normalization(self, ingester, tmp_path):
        """Test that column names are normalized (lowercase, stripped)."""
        csv_content = """Ticker,  Timestamp  ,OPEN,HIGH,Low,CLOSE,Volume
AAPL,2024-01-02 09:30:00,185.50,186.00,185.00,185.75,1000000
"""
        csv_file = tmp_path / "weird_cols.csv"
        csv_file.write_text(csv_content)
        
        df = ingester.load_csv(csv_file)
        
        assert 'ticker' in df.columns
        assert 'timestamp' in df.columns
        assert len(df) == 1


class TestOHLCVRecord:
    """Tests for OHLCVRecord dataclass."""
    
    def test_record_creation(self):
        """Test creating an OHLCV record."""
        record = OHLCVRecord(
            ticker='AAPL',
            timestamp=datetime(2024, 1, 2, 9, 30, 0),
            open=185.50,
            high=186.00,
            low=185.00,
            close=185.75,
            volume=1000000,
        )
        
        assert record.ticker == 'AAPL'
        assert record.open == 185.50
        assert record.volume == 1000000
