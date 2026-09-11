"""
export_analytics.py

Runs the cohort retention and funnel SQL against PostgreSQL and exports the
results to data/analytics_outputs/*.csv. This is the ONLY script that needs
a database connection - the Streamlit dashboard reads exclusively from the
CSVs this script produces, so it can be deployed (e.g. to Streamlit Cloud)
with zero database credentials.

Also builds the pivoted cohort table (cohort_month x months_since_cohort ->
retention_rate) used by the Plotly heatmap. This pivot is done in pandas
rather than SQL (e.g. via the tablefunc/crosstab extension) so it doesn't
require a Postgres extension to be installed/enabled.

Usage:
    python scripts/export_analytics.py
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = BASE_DIR / "sql"
OUT_DIR = BASE_DIR / "data" / "analytics_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "amazon_analytics"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}


def get_connection():
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
    )
    engine = create_engine(url)
    return engine.connect()


def run_query_to_df(conn, sql_path: Path) -> pd.DataFrame:
    with open(sql_path, "r") as f:
        query = f.read()
    return pd.read_sql_query(query, conn)


def export_cohort_retention(conn):
    df = run_query_to_df(conn, SQL_DIR / "03_cohort_retention.sql")
    df.to_csv(OUT_DIR / "cohort_retention.csv", index=False)
    print(f"  cohort_retention.csv          ({len(df)} rows)")

    pivot = df.pivot(index="cohort_month", columns="months_since_cohort", values="retention_rate")
    pivot = pivot.sort_index()
    pivot.columns = [f"month_{c}" for c in pivot.columns]
    pivot.to_csv(OUT_DIR / "cohort_retention_pivot.csv")
    print(f"  cohort_retention_pivot.csv    ({pivot.shape[0]} cohorts x {pivot.shape[1]} month offsets)")


def export_funnel_fulfillment(conn):
    df = run_query_to_df(conn, SQL_DIR / "04_funnel_analysis.sql")
    df.to_csv(OUT_DIR / "funnel_fulfillment.csv", index=False)
    print(f"  funnel_fulfillment.csv        ({len(df)} rows, REAL data)")


def export_kpi_summary(conn):
    """A small denormalized summary the dashboard can load in one shot for
    top-line KPI tiles, computed straight from the real tables."""
    query = """
        SELECT
            (SELECT COUNT(DISTINCT customer_id) FROM customers) AS total_customers,
            (SELECT COUNT(DISTINCT customer_id) FROM orders) AS customers_with_orders,
            (SELECT COUNT(*) FROM orders) AS total_orders,
            (SELECT ROUND(SUM(total_sale)::numeric, 2) FROM order_items) AS total_revenue,
            (SELECT ROUND(AVG(total_sale)::numeric, 2) FROM order_items) AS avg_order_value,
            (SELECT MIN(order_date) FROM orders) AS first_order_date,
            (SELECT MAX(order_date) FROM orders) AS last_order_date,
            (SELECT COUNT(*) FROM products) AS total_products,
            (SELECT COUNT(*) FROM sellers) AS total_sellers
    """
    df = pd.read_sql_query(query, conn)
    df.to_csv(OUT_DIR / "kpi_summary.csv", index=False)
    print(f"  kpi_summary.csv               (1 row)")


def main():
    print(f"Connecting to postgresql://{DB_CONFIG['user']}@{DB_CONFIG['host']}:"
          f"{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    conn = get_connection()
    try:
        print("Exporting analytics outputs to data/analytics_outputs/ ...")
        export_kpi_summary(conn)
        export_cohort_retention(conn)
        export_funnel_fulfillment(conn)
        print("Done. (Run scripts/simulate_discovery_funnel.py and "
              "scripts/ab_test_simulation.py next.)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
