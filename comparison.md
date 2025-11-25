# Format Comparison: SQLite vs Parquet

## Size
- SQLite (`market_data.db`): 1.6 MB for 9,775 rows across 5 tickers.
- Parquet (`market_data/` partitioned by ticker): 344 KB (80% smaller due to columnar compression and partition pruning).

## Query Speed (sample benchmarks)
- Date-range query (AAPL, 2025-11-17 → 2025-11-18, 5 runs, warm cache): SQLite ~6.0 ms avg; Parquet ~8.8 ms avg (min 1.2 ms, variance from filesystem discovery).
- Full ticker load: SQLite ~6.8 ms; Parquet ~1.2 ms.
- Volatility on Parquet (5-bar rolling): ~2.1 ms.
- Takeaway: SQLite excels on repeated indexed lookups; Parquet shines on full scans, aggregations, and vectorized analytics.

## Workflow Fit
- SQLite
  - Strengths: ACID, constraints, easy upserts, indexed point/range lookups, concurrent reads, integrates with SQL clients and dashboards.
  - Best for: lightweight services, ETL staging, production lookups, scenarios needing referential integrity (e.g., ticker metadata joins).
- Parquet
  - Strengths: Columnar compression, predicate pushdown, partition pruning by ticker, fast column slicing for analytics, interoperable with pandas/Arrow/Spark/Polars.
  - Best for: research notebooks, backtests, feature generation, bulk analytics and model inputs.

## Guidance
- Use SQLite when write patterns and integrity matter, or when serving many small range queries (e.g., intraday chart API).
- Use Parquet when scanning many columns/rows, computing rolling stats (volatility/averages), or exchanging data across Python data tools.
- Hybrid approach: ingest → validate once, write both backends (via `data_loader.py`), and route queries through `QueryEngine` to choose the optimal backend per task.
