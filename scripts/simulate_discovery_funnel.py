"""
simulate_discovery_funnel.py

Generates a SIMULATED / ILLUSTRATIVE "Product Discovery Funnel":
    View Item -> Add to Cart -> Checkout -> Purchase

WHY THIS IS SIMULATED, NOT REAL:
This schema has no clickstream or event-tracking table of any kind - there
is no page-view, add-to-cart, or checkout-initiation data anywhere in the
source project. The REAL funnel this schema supports is the order
fulfillment lifecycle in sql/04_funnel_analysis.sql / funnel_fulfillment.csv,
which should be treated as the primary funnel in this project. This file
exists only to illustrate what a top-of-funnel view COULD look like using
documented industry benchmarks - it is not, and must never be presented
as, observed customer behavior.

Safeguards against this being mistaken for real data, all applied below:
  1. Every stage label ends in "(Simulated)".
  2. Every numeric estimate is rounded to the nearest 50 - deliberately
     imprecise, unlike a real measured count, which would not round so
     cleanly.
  3. Every row carries is_simulated = True and a `methodology` string
     explaining how the number was produced.
  4. Only the Purchase stage is tied to real data (the actual completed-
     order count) - View Item / Add to Cart / Checkout are computed
     backwards from documented, generic industry-average e-commerce
     conversion benchmarks (not measurements of this business), with
     reproducible random noise (fixed seed) so the numbers don't look
     artificially exact.

Usage:
    python scripts/simulate_discovery_funnel.py
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "data" / "analytics_outputs"

SEED = 42
ROUND_TO_NEAREST = 50  # deliberately coarse - real observed counts would not be this round

# Documented, industry-average e-commerce step conversion rates (source:
# widely-cited benchmarks e.g. Baymard Institute / Shopify commerce reports
# for View->Cart, Cart->Checkout-start, Checkout-start->Purchase). These are
# GENERIC industry benchmarks, not measurements of this dataset, and are
# used only to sketch a plausible, clearly-labeled illustrative funnel.
ASSUMED_RATES = {
    "cart_to_checkout": 0.55,      # of users who add to cart, % who start checkout
    "checkout_to_purchase": 0.75,  # of users who start checkout, % who purchase
    "view_to_cart": 0.28,          # of users who view a product, % who add to cart
}

METHODOLOGY_ANCHOR = (
    "REAL - matches the 'Kept (Not Returned)' stage of funnel_fulfillment.csv"
)
METHODOLOGY_ESTIMATED = (
    "SIMULATED - backed out from generic industry-average e-commerce "
    "conversion benchmarks, not measured from this dataset (no clickstream "
    "data exists in this schema)"
)


def load_real_purchase_count() -> int:
    """Pull the real 'Kept (Not Returned)' order count exported by the
    funnel SQL, so the bottom of the simulated funnel is anchored to data."""
    fulfillment_path = OUT_DIR / "funnel_fulfillment.csv"
    df = pd.read_csv(fulfillment_path)
    kept_row = df[df["stage"] == "Kept (Not Returned)"]
    if kept_row.empty:
        raise ValueError("Could not find 'Kept (Not Returned)' stage in funnel_fulfillment.csv")
    return int(kept_row.iloc[0]["orders"])


def _round_estimate(x: float) -> int:
    return int(round(x / ROUND_TO_NEAREST) * ROUND_TO_NEAREST)


def simulate_funnel(real_purchases: int, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    purchases = real_purchases  # REAL number, anchor point - not rounded

    # Work backwards with small reproducible noise around the assumed rates
    checkout_rate = ASSUMED_RATES["checkout_to_purchase"] * rng.uniform(0.97, 1.03)
    cart_rate = ASSUMED_RATES["cart_to_checkout"] * rng.uniform(0.97, 1.03)
    view_rate = ASSUMED_RATES["view_to_cart"] * rng.uniform(0.97, 1.03)

    checkouts = _round_estimate(purchases / checkout_rate)
    carts = _round_estimate(checkouts / cart_rate)
    views = _round_estimate(carts / view_rate)

    stages = [
        ("View Item (Simulated)", 1, views, METHODOLOGY_ESTIMATED),
        ("Add to Cart (Simulated)", 2, carts, METHODOLOGY_ESTIMATED),
        ("Checkout (Simulated)", 3, checkouts, METHODOLOGY_ESTIMATED),
        ("Purchase (Real, Anchor Point)", 4, purchases, METHODOLOGY_ANCHOR),
    ]

    rows = []
    prev_users = None
    for stage, order, users, methodology in stages:
        drop_off = None if prev_users is None else prev_users - users
        conv_prev = None if prev_users is None else round(users / prev_users * 100, 2)
        conv_start = round(users / views * 100, 2)
        rows.append({
            "stage": stage,
            "stage_order": order,
            "estimated_users": users,
            "drop_off": drop_off,
            "conversion_from_previous_pct": conv_prev,
            "conversion_from_start_pct": conv_start,
            "is_simulated": True,
            "methodology": methodology,
        })
        prev_users = users

    return pd.DataFrame(rows)


def main():
    real_purchases = load_real_purchase_count()
    df = simulate_funnel(real_purchases)
    out_path = OUT_DIR / "funnel_discovery_simulated.csv"
    df.to_csv(out_path, index=False)
    print(f"Simulated/illustrative discovery funnel written to {out_path}")
    print(f"(Purchase stage anchored to {real_purchases} REAL completed orders; "
          f"all other stages are illustrative estimates, rounded to the "
          f"nearest {ROUND_TO_NEAREST} so they are not mistaken for exact "
          f"measured counts)")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
