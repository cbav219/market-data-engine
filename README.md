# market-data-engine

Python system for ingesting, storing, and querying multi-ticker market data using SQLite3 and Parquet. Demonstrates tradeoffs between relational and columnar formats, with focus on schema design, efficient queries, and format selection for quantitative finance, analytics, and trading workflows.

## Features

- **CSV Data Ingestion**: Load and validate OHLCV (Open, High, Low, Close, Volume) market data from CSV files
- **Data Validation**: Check timestamps, prices (including OHLC relationship), volume, and ticker completeness
- **SQLite Storage**: Normalized schema with tickers and prices tables, foreign keys, and indexes
- **Parquet Storage**: Columnar format with ticker partitioning for efficient analytics
- **Query Engine**: Unified interface for both storage backends
- **Benchmark Tools**: Compare performance between SQLite and Parquet

## Installation

```bash
pip install -e ".[dev]"
```

## Assignment Workflow (SQLite + Parquet)

```bash
# 1) Build both backends from provided data
PYTHONPATH=src python -m market_data_engine.data_loader

# Artifacts created:
#   - market_data.db (SQLite, schema in schema.sql)
#   - market_data/ (Parquet, partitioned by ticker)

# 2) Run sample queries via QueryEngine
PYTHONPATH=src python - <<'PY'
from datetime import datetime
from market_data_engine import QueryEngine, SQLiteStorage, ParquetStorage

engine = QueryEngine(SQLiteStorage("market_data.db"), ParquetStorage("market_data"))

start = datetime(2025, 11, 17)
end = datetime(2025, 11, 18, 23, 59, 59)

print(engine.get_price_range("TSLA", start, end).head())                 # task 1
print(engine.get_avg_daily_volume())                                     # task 2
print(engine.get_top_tickers_by_return(start, end, source="sqlite"))     # task 3
print(engine.get_first_last_prices_per_day().head())                     # task 4
print(engine.get_rolling_close_average("AAPL", window=5, source="parquet").head())  # parquet rolling avg
print(engine.get_volatility(None, window=5, source="parquet").head())    # parquet volatility all tickers
PY
```

## Quick Start

```python
from market_data_engine import CSVIngester, SQLiteStorage, ParquetStorage, QueryEngine
from datetime import datetime

# Load CSV data with validation (uses provided market_data_multi.csv)
ingester = CSVIngester(expected_tickers={'AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN'})
df = ingester.load_csv('market_data_multi.csv')

# Store in SQLite
sqlite_storage = SQLiteStorage('market_data.db')
sqlite_storage.insert_data(df)

# Store in Parquet with ticker partitions
parquet_storage = ParquetStorage('parquet_data/')
parquet_storage.save_data(df, partition_by_ticker=True)

# Query using unified interface
engine = QueryEngine(sqlite_storage, parquet_storage)

# Get price range
prices = engine.get_price_range(
    'AAPL',
    datetime(2024, 1, 2),
    datetime(2024, 1, 5),
    source='sqlite'  # or 'parquet'
)

# Get average volume
avg_vol = engine.get_avg_volume('AAPL', source='sqlite')

# Get weekly returns
weekly = engine.get_weekly_returns('AAPL', source='sqlite')

# Get daily first/last prices
daily = engine.get_daily_first_last_prices('AAPL', source='sqlite')

# Compute 5-day rolling volatility (optimized for Parquet)
volatility = engine.get_volatility('AAPL', window=5, source='parquet')
```

## Files and Deliverables

- `market_data_engine/data_loader.py`: one-shot ingest/validate + dual-write to SQLite (`market_data.db`) and Parquet (`market_data/`).
- `schema.sql`: SQLite schema aligned with the implementation (tickers + prices, indexes).
- `query_tasks.md`: Filled with query outputs and performance notes.
- `comparison.md`: Format tradeoff analysis (size, speed, workflow guidance).
- `tests/`: Pytest suite (ingestion, SQLite, Parquet, query routing, benchmarks).

## Data Validation

The `CSVIngester` validates:
- Required columns: ticker, timestamp, open, high, low, close, volume
- Timestamp format and uniqueness (no duplicate ticker + timestamp)
- Price range (non-negative, within reasonable bounds)
- OHLC relationship (high >= low, open, close)
- Volume (non-negative)
- Ticker completeness (all expected tickers present)

```python
from market_data_engine import CSVIngester, ValidationError

ingester = CSVIngester(
    expected_tickers={'AAPL', 'GOOGL'},
    timestamp_format='%Y-%m-%d %H:%M:%S',
    min_price=0.0,
    max_price=1_000_000.0,
)

try:
    df = ingester.load_csv('data.csv')
except ValidationError as e:
    print(f"Validation failed: {e}")
```

## SQLite Schema

```sql
-- Tickers table
CREATE TABLE tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prices table with foreign key
CREATE TABLE prices (
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
);

-- Indexes for efficient querying
CREATE INDEX idx_prices_ticker_id ON prices(ticker_id);
CREATE INDEX idx_prices_timestamp ON prices(timestamp);
CREATE INDEX idx_prices_ticker_timestamp ON prices(ticker_id, timestamp);
```

## Parquet Storage

Data is stored with ticker-based partitioning:
```
parquet_data/
├── ticker=AAPL/
│   └── *.parquet
├── ticker=GOOGL/
│   └── *.parquet
└── ticker=MSFT/
    └── *.parquet
```

Verify data integrity:
```python
integrity = parquet_storage.verify_integrity()
print(f"Valid: {integrity['valid']}")
print(f"Records: {integrity['total_records']}")
print(f"Tickers: {integrity['tickers']}")
```

## Benchmarking

```python
from market_data_engine.parquet_storage import benchmark_parquet_vs_sqlite

results = benchmark_parquet_vs_sqlite(
    df,
    sqlite_storage,
    parquet_storage,
    ticker='AAPL',
    iterations=10,
)

print(f"SQLite date range: {results['sqlite']['date_range_query']['avg_time']*1000:.2f}ms")
print(f"Parquet date range: {results['parquet']['date_range_query']['avg_time']*1000:.2f}ms")
```

## Running Tests

```bash
pytest tests/ -v
```

## License

MIT
