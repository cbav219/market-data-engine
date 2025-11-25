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
                    ticker_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT UNIQUE NOT NULL,
                    name TEXT,
                    exchange TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create prices table with foreign key to tickers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id),
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
            conn = self._persistent_conn
        else:
            # For file-based databases, create a new connection
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            if not self._is_memory:
                conn.close()
    
    def insert_ticker(self, symbol: str, name: Optional[str] = None, exchange: Optional[str] = None) -> int:
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
            cursor.execute("SELECT ticker_id FROM tickers WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                return row['ticker_id']
            
            # Insert new ticker
            cursor.execute(
                "INSERT INTO tickers (symbol, name, exchange) VALUES (?, ?, ?)",
                (symbol, name, exchange)
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
            cursor.execute("SELECT ticker_id, symbol, name, exchange, created_at FROM tickers")
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
                JOIN tickers t ON p.ticker_id = t.ticker_id
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
                JOIN tickers t ON p.ticker_id = t.ticker_id
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
                JOIN tickers t ON p.ticker_id = t.ticker_id
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
        return self.get_first_last_prices_per_day(ticker=ticker)
    
    def get_first_last_prices_per_day(self, ticker: Optional[str] = None) -> pd.DataFrame:
        """
        Get first and last trade prices per day, optionally filtered by ticker.
        
        Args:
            ticker: Optional ticker symbol to filter.
            
        Returns:
            DataFrame with ticker, date, first_timestamp, first_price, last_timestamp, last_price.
        """
        with self._get_connection() as conn:
            params = []
            ticker_filter = ""
            if ticker:
                ticker_filter = "WHERE t.symbol = ?"
                params.append(ticker)
            
            query = f"""
                WITH ordered AS (
                    SELECT 
                        t.symbol AS ticker,
                        DATE(p.timestamp) AS trade_date,
                        p.timestamp,
                        p.open,
                        p.close,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.symbol, DATE(p.timestamp)
                            ORDER BY p.timestamp
                        ) AS rn_first,
                        ROW_NUMBER() OVER (
                            PARTITION BY t.symbol, DATE(p.timestamp)
                            ORDER BY p.timestamp DESC
                        ) AS rn_last
                    FROM prices p
                    JOIN tickers t ON p.ticker_id = t.ticker_id
                    {ticker_filter}
                )
                SELECT 
                    ticker,
                    trade_date AS date,
                    MAX(CASE WHEN rn_first = 1 THEN timestamp END) AS first_timestamp,
                    MAX(CASE WHEN rn_first = 1 THEN open END) AS first_price,
                    MAX(CASE WHEN rn_last = 1 THEN timestamp END) AS last_timestamp,
                    MAX(CASE WHEN rn_last = 1 THEN close END) AS last_price
                FROM ordered
                GROUP BY ticker, trade_date
                ORDER BY ticker, trade_date
            """
            df = pd.read_sql_query(query, conn, params=params)
            
            if df.empty:
                return df
            
            df['first_timestamp'] = pd.to_datetime(df['first_timestamp'])
            df['last_timestamp'] = pd.to_datetime(df['last_timestamp'])
            return df
    
    def get_avg_daily_volume(self) -> pd.DataFrame:
        """
        Calculate average daily volume per ticker.
        
        Returns:
            DataFrame with ticker and avg_daily_volume.
        """
        with self._get_connection() as conn:
            query = """
                WITH daily AS (
                    SELECT 
                        t.symbol AS ticker,
                        DATE(p.timestamp) AS trade_date,
                        SUM(p.volume) AS daily_volume
                    FROM prices p
                    JOIN tickers t ON p.ticker_id = t.ticker_id
                    GROUP BY t.symbol, DATE(p.timestamp)
                )
                SELECT 
                    ticker, 
                    AVG(daily_volume) AS avg_daily_volume
                FROM daily
                GROUP BY ticker
                ORDER BY ticker
            """
            return pd.read_sql_query(query, conn)
    
    def get_top_tickers_by_return(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 3,
    ) -> pd.DataFrame:
        """
        Identify top tickers by return over a given window.
        
        Args:
            start_date: Start date (inclusive).
            end_date: End date (inclusive).
            limit: Number of tickers to return.
            
        Returns:
            DataFrame with ticker and return_pct columns.
        """
        with self._get_connection() as conn:
            query = """
                WITH filtered AS (
                    SELECT 
                        p.timestamp,
                        p.open,
                        p.close,
                        p.ticker_id,
                        t.symbol
                    FROM prices p
                    JOIN tickers t ON p.ticker_id = t.ticker_id
                    WHERE p.timestamp >= ? AND p.timestamp <= ?
                ),
                first_trade AS (
                    SELECT f.symbol, f.open AS first_open
                    FROM filtered f
                    JOIN (
                        SELECT symbol, MIN(timestamp) AS min_ts
                        FROM filtered
                        GROUP BY symbol
                    ) mins
                    ON f.symbol = mins.symbol AND f.timestamp = mins.min_ts
                ),
                last_trade AS (
                    SELECT f.symbol, f.close AS last_close
                    FROM filtered f
                    JOIN (
                        SELECT symbol, MAX(timestamp) AS max_ts
                        FROM filtered
                        GROUP BY symbol
                    ) maxs
                    ON f.symbol = maxs.symbol AND f.timestamp = maxs.max_ts
                )
                SELECT 
                    f.symbol AS ticker,
                    ((l.last_close - f.first_open) / f.first_open) * 100 AS return_pct
                FROM first_trade f
                JOIN last_trade l ON f.symbol = l.symbol
                ORDER BY return_pct DESC
                LIMIT ?
            """
            df = pd.read_sql_query(
                query,
                conn,
                params=(start_date.isoformat(), end_date.isoformat(), limit),
            )
            return df
    
    def close(self) -> None:
        """Close the database connection."""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
