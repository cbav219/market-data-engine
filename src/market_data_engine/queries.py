"""Query engine module for OHLCV market data."""

from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd

from .sqlite_storage import SQLiteStorage
from .parquet_storage import ParquetStorage


class QueryEngine:
    """Unified query interface for both SQLite and Parquet storage."""
    
    def __init__(
        self,
        sqlite_storage: Optional[SQLiteStorage] = None,
        parquet_storage: Optional[ParquetStorage] = None,
    ):
        """
        Initialize the query engine.
        
        Args:
            sqlite_storage: SQLite storage instance.
            parquet_storage: Parquet storage instance.
        """
        self.sqlite = sqlite_storage
        self.parquet = parquet_storage
    
    def get_price_range(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        source: str = "sqlite",
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a ticker within a date range.
        
        Args:
            ticker: Ticker symbol.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            source: Data source ("sqlite" or "parquet").
            
        Returns:
            DataFrame with OHLCV data.
        """
        if source == "sqlite" and self.sqlite:
            return self.sqlite.get_price_range(ticker, start_date, end_date)
        elif source == "parquet" and self.parquet:
            return self.parquet.get_date_range(ticker, start_date, end_date)
        else:
            raise ValueError(f"Invalid or unavailable source: {source}")
    
    def get_avg_volume(self, ticker: str, source: str = "sqlite") -> float:
        """
        Get average volume for a ticker.
        
        Args:
            ticker: Ticker symbol.
            source: Data source ("sqlite" or "parquet").
            
        Returns:
            Average volume.
        """
        if source == "sqlite" and self.sqlite:
            return self.sqlite.get_avg_volume(ticker)
        elif source == "parquet" and self.parquet:
            df = self.parquet.load_data(ticker)
            return df['volume'].mean() if not df.empty else 0.0
        else:
            raise ValueError(f"Invalid or unavailable source: {source}")
    
    def get_weekly_returns(self, ticker: str, source: str = "sqlite") -> pd.DataFrame:
        """
        Calculate weekly returns for a ticker.
        
        Args:
            ticker: Ticker symbol.
            source: Data source ("sqlite" or "parquet").
            
        Returns:
            DataFrame with weekly returns.
        """
        if source == "sqlite" and self.sqlite:
            return self.sqlite.get_weekly_returns(ticker)
        elif source == "parquet" and self.parquet:
            df = self.parquet.load_data(ticker)
            if df.empty:
                return pd.DataFrame(columns=[
                    'week_start', 'week_end', 'first_open', 'last_close', 'weekly_return'
                ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['week'] = df['timestamp'].dt.isocalendar().week
            df['year'] = df['timestamp'].dt.isocalendar().year
            
            weekly_data = []
            for (year, week), group in df.groupby(['year', 'week']):
                group = group.sort_values('timestamp')
                first_row = group.iloc[0]
                last_row = group.iloc[-1]
                
                weekly_return = (last_row['close'] - first_row['open']) / first_row['open'] * 100
                
                weekly_data.append({
                    'week_start': first_row['timestamp'],
                    'week_end': last_row['timestamp'],
                    'first_open': first_row['open'],
                    'last_close': last_row['close'],
                    'weekly_return': weekly_return,
                })
            
            return pd.DataFrame(weekly_data)
        else:
            raise ValueError(f"Invalid or unavailable source: {source}")
    
    def get_daily_first_last_prices(
        self,
        ticker: str,
        source: str = "sqlite",
    ) -> pd.DataFrame:
        """
        Get daily first and last prices for a ticker.
        
        Args:
            ticker: Ticker symbol.
            source: Data source ("sqlite" or "parquet").
            
        Returns:
            DataFrame with daily first and last prices.
        """
        if source == "sqlite" and self.sqlite:
            return self.sqlite.get_daily_first_last_prices(ticker)
        elif source == "parquet" and self.parquet:
            df = self.parquet.load_data(ticker)
            if df.empty:
                return pd.DataFrame(columns=[
                    'date', 'first_timestamp', 'first_price', 
                    'last_timestamp', 'last_price'
                ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = df['timestamp'].dt.date
            
            daily_data = []
            for date, group in df.groupby('date'):
                group = group.sort_values('timestamp')
                first_row = group.iloc[0]
                last_row = group.iloc[-1]
                
                daily_data.append({
                    'date': date,
                    'first_timestamp': first_row['timestamp'],
                    'first_price': first_row['open'],
                    'last_timestamp': last_row['timestamp'],
                    'last_price': last_row['close'],
                })
            
            return pd.DataFrame(daily_data)
        else:
            raise ValueError(f"Invalid or unavailable source: {source}")
    
    def get_volatility(
        self,
        ticker: str,
        window: int = 5,
        source: str = "parquet",
    ) -> pd.DataFrame:
        """
        Compute rolling volatility for a ticker.
        
        Args:
            ticker: Ticker symbol.
            window: Rolling window size.
            source: Data source (default "parquet" for efficiency).
            
        Returns:
            DataFrame with volatility data.
        """
        if source == "parquet" and self.parquet:
            return self.parquet.compute_volatility(ticker, window)
        elif source == "sqlite" and self.sqlite:
            # Load data from SQLite and compute
            from datetime import datetime, timedelta
            start = datetime(2000, 1, 1)
            end = datetime(2100, 12, 31)
            df = self.sqlite.get_price_range(ticker, start, end)
            
            if df.empty or len(df) < 2:
                return pd.DataFrame(columns=['timestamp', 'close', 'daily_return', 'volatility'])
            
            df = df.sort_values('timestamp').reset_index(drop=True)
            df['daily_return'] = df['close'].pct_change()
            df['volatility'] = df['daily_return'].rolling(window=window).std()
            
            return df[['timestamp', 'close', 'daily_return', 'volatility']]
        else:
            raise ValueError(f"Invalid or unavailable source: {source}")
    
    def compare_sources(self, ticker: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Compare data from SQLite and Parquet sources.
        
        Args:
            ticker: Ticker symbol.
            start_date: Start date.
            end_date: End date.
            
        Returns:
            Dictionary with comparison results.
        """
        results = {
            'ticker': ticker,
            'date_range': (start_date.isoformat(), end_date.isoformat()),
            'sqlite': {},
            'parquet': {},
            'match': False,
        }
        
        if self.sqlite:
            sqlite_df = self.sqlite.get_price_range(ticker, start_date, end_date)
            results['sqlite'] = {
                'record_count': len(sqlite_df),
                'columns': list(sqlite_df.columns),
            }
        
        if self.parquet:
            parquet_df = self.parquet.get_date_range(ticker, start_date, end_date)
            results['parquet'] = {
                'record_count': len(parquet_df),
                'columns': list(parquet_df.columns),
            }
        
        if results['sqlite'] and results['parquet']:
            results['match'] = results['sqlite']['record_count'] == results['parquet']['record_count']
        
        return results
