"""
load_data.py

Loads the raw CSVs in data/raw/ into a PostgreSQL database, after applying
the schema in sql/01_schema.sql.

This script exists because the raw CSVs have real-world messiness that
needs to be handled before they can be loaded into the schema:
  - Several files are saved with a UTF-8 BOM, which prepends an invisible
    character to the first header (e.g. "Customer ID" instead of the
    expected "customer_id").
  - Header names/casing don't always match the schema column names
    (e.g. "Customer ID" -> customer_id, "shipping providers" ->
    shipping_providers).
  - order_items.total_sale is a generated column in the schema, so it must
    NOT be included in the insert.

Connection settings are read from environment variables (see .env.example)
so no credentials are hard-coded here.

Usage:
    python scripts/load_data.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set directly instead

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
SCHEMA_FILE = BASE_DIR / "sql" / "01_schema.sql"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "amazon_analytics"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def run_schema(conn):
    print("Applying schema from sql/01_schema.sql ...")
    with open(SCHEMA_FILE, "r") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema applied.")


def read_clean_csv(filename, rename_map=None):
    """Read a CSV, strip BOM/whitespace from headers, apply rename_map."""
    df = pd.read_csv(RAW_DIR / filename, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _to_native(value):
    """Convert numpy/pandas scalar types to plain Python types for psycopg2."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def load_table(conn, df, table, columns):
    """Bulk-insert a dataframe into a table using execute_values."""
    df = df[columns].where(pd.notnull(df[columns]), None)
    records = [tuple(_to_native(v) for v in row) for row in df.to_numpy()]
    col_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, sql, records, page_size=2000)
    conn.commit()
    print(f"  loaded {len(records):>6} rows -> {table}")


def main():
    print(f"Connecting to postgresql://{DB_CONFIG['user']}@{DB_CONFIG['host']}:"
          f"{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    conn = get_connection()
    try:
        run_schema(conn)

        print("Loading tables (in FK-safe order) ...")

        category = read_clean_csv("category.csv")
        load_table(conn, category, "category", ["category_id", "category_name"])

        customers = read_clean_csv("customers.csv", rename_map={"Customer ID": "customer_id"})
        load_table(conn, customers, "customers", ["customer_id", "first_name", "last_name", "state"])

        sellers = read_clean_csv("sellers.csv")
        load_table(conn, sellers, "sellers", ["seller_id", "seller_name", "origin"])

        products = read_clean_csv("products.csv")
        load_table(conn, products, "products",
                   ["product_id", "product_name", "price", "cogs", "category_id"])

        inventory = read_clean_csv("inventory.csv")
        load_table(conn, inventory, "inventory",
                   ["inventory_id", "product_id", "stock", "warehouse_id", "last_stock_date"])

        orders = read_clean_csv("orders.csv")
        load_table(conn, orders, "orders",
                   ["order_id", "order_date", "customer_id", "seller_id", "order_status"])

        order_items = read_clean_csv("order_items.csv")
        # total_sale is a GENERATED column - must not be inserted explicitly
        load_table(conn, order_items, "order_items",
                   ["order_item_id", "order_id", "product_id", "quantity", "price_per_unit"])

        payments = read_clean_csv("payments.csv")
        load_table(conn, payments, "payments",
                   ["payment_id", "order_id", "payment_date", "payment_status"])

        shipping = read_clean_csv(
            "shipping.csv",
            rename_map={"shipping providers": "shipping_providers"},
        )
        load_table(conn, shipping, "shippings",
                   ["shipping_id", "order_id", "shipping_date", "return_date",
                    "shipping_providers", "delivery_status"])

        print("\nAll tables loaded successfully.")

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders;")
            n_orders = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM order_items WHERE total_sale IS NULL;")
            n_null_sale = cur.fetchone()[0]
        print(f"Sanity check: {n_orders} orders loaded; {n_null_sale} order_items "
              f"missing a generated total_sale (should be 0).")

    except Exception as e:
        conn.rollback()
        print(f"ERROR during load: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
