"""SQLite storage module for OHLCV market data."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Any, Iterator

import pandas as pd


class SQLiteStorage:
    """SQLite-based storage for OHLCV market data."""
    
    def __init__(self, db_path: str | Path = ":memory:"):
        """
        Initialize the SQLite storage.
        
        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory database.
        """
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:"
        self._persistent_conn: Optional[sqlite3.Connection] = None
        
        # For in-memory databases, create and keep a persistent connection
        if self._is_memory:
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
        
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Initialize database with required tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tickers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT UNIQUE NOT NULL,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create prices table with foreign key to tickers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker_id INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    FOREIGN KEY (ticker_id) REFERENCES tickers(id),
                    UNIQUE(ticker_id, timestamp)
                )
            """)
            
            # Create indexes for efficient querying
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_ticker_id 
                ON prices(ticker_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_timestamp 
                ON prices(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_ticker_timestamp 
                ON prices(ticker_id, timestamp)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with context manager."""
        if self._is_memory and self._persistent_conn:
            # For in-memory databases, use the persistent connection
            yield self._persistent_conn
        else:
            # For file-based databases, create a new connection
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    def insert_ticker(self, symbol: str, name: Optional[str] = None) -> int:
        """
        Insert a new ticker or return existing ticker ID.
        
        Args:
            symbol: Ticker symbol.
            name: Optional ticker name.
            
        Returns:
            Ticker ID.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to get existing ticker
            cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                return row['id']
            
            # Insert new ticker
            cursor.execute(
                "INSERT INTO tickers (symbol, name) VALUES (?, ?)",
                (symbol, name)
            )
            conn.commit()
            return cursor.lastrowid
    
    def insert_data(self, df: pd.DataFrame) -> int:
        """
        Insert OHLCV data from a DataFrame.
        
        Args:
            df: DataFrame with columns: ticker, timestamp, open, high, low, close, volume.
            
        Returns:
            Number of rows inserted.
        """
        rows_inserted = 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get or create ticker IDs
            ticker_ids = {}
            for ticker in df['ticker'].unique():
                ticker_ids[ticker] = self.insert_ticker(ticker)
            
            # Insert price data
            for _, row in df.iterrows():
                ticker_id = ticker_ids[row['ticker']]
                timestamp = row['timestamp']
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO prices 
                        (ticker_id, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ticker_id,
                        timestamp,
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume']),
                    ))
                    rows_inserted += 1
                except sqlite3.Error as e:
                    print(f"Error inserting row: {e}")
            
            conn.commit()
        
        return rows_inserted
    
    def get_tickers(self) -> List[dict]:
        """Get all tickers."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, symbol, name, created_at FROM tickers")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_price_range(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Get OHLCV data for a ticker within a date range.
        
        Args:
            ticker: Ticker symbol.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            
        Returns:
            DataFrame with OHLCV data.
        """
        with self._get_connection() as conn:
            query = """
                SELECT t.symbol as ticker, p.timestamp, p.open, p.high, 
                       p.low, p.close, p.volume
                FROM prices p
                JOIN tickers t ON p.ticker_id = t.id
                WHERE t.symbol = ?
                AND p.timestamp >= ?
                AND p.timestamp <= ?
                ORDER BY p.timestamp
            """
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(ticker, start_date.isoformat(), end_date.isoformat())
            )
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
    
    def get_avg_volume(self, ticker: str) -> float:
        """
        Get average volume for a ticker.
        
        Args:
            ticker: Ticker symbol.
            
        Returns:
            Average volume.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT AVG(p.volume) as avg_volume
                FROM prices p
                JOIN tickers t ON p.ticker_id = t.id
                WHERE t.symbol = ?
            """, (ticker,))
            row = cursor.fetchone()
            return row['avg_volume'] if row and row['avg_volume'] else 0.0
    
    def get_weekly_returns(self, ticker: str) -> pd.DataFrame:
        """
        Calculate weekly returns for a ticker.
        
        Args:
            ticker: Ticker symbol.
            
        Returns:
            DataFrame with week_start, week_end, first_open, last_close, weekly_return.
        """
        with self._get_connection() as conn:
            # Get all prices for ticker
            query = """
                SELECT p.timestamp, p.open, p.close
                FROM prices p
                JOIN tickers t ON p.ticker_id = t.id
                WHERE t.symbol = ?
                ORDER BY p.timestamp
            """
            df = pd.read_sql_query(query, conn, params=(ticker,))
            
            if df.empty:
                return pd.DataFrame(columns=[
                    'week_start', 'week_end', 'first_open', 'last_close', 'weekly_return'
                ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['week'] = df['timestamp'].dt.isocalendar().week
            df['year'] = df['timestamp'].dt.isocalendar().year
            
            # Group by year-week
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
    
    def get_daily_first_last_prices(self, ticker: str) -> pd.DataFrame:
        """
        Get daily first and last prices for a ticker.
        
        Args:
            ticker: Ticker symbol.
            
        Returns:
            DataFrame with date, first_timestamp, first_price, last_timestamp, last_price.
        """
        with self._get_connection() as conn:
            query = """
                SELECT p.timestamp, p.open, p.close
                FROM prices p
                JOIN tickers t ON p.ticker_id = t.id
                WHERE t.symbol = ?
                ORDER BY p.timestamp
            """
            df = pd.read_sql_query(query, conn, params=(ticker,))
            
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
    
    def close(self) -> None:
        """Close the database connection."""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
