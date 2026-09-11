# Amazon E-Commerce Product Analytics

A product analytics case study built on a real 21,629-order e-commerce dataset: **cohort retention**, **funnel analysis**, and a **simulated A/B test**, served through a PostgreSQL → SQL → CSV → Streamlit/Plotly pipeline.

This project is an upgrade of an earlier advanced-SQL practice repository (19 business-question queries against a 9-table PostgreSQL schema) into a Product Analyst-style case study, aimed at Product Analyst / Data Analyst roles at companies like Amazon, Zomato, Swiggy, and Flipkart.

> **Analytical QA pass:** after the initial build, this project went through a dedicated correctness review that tightened three things: (1) cohort retention now counts only orders where payment actually succeeded, instead of counting cancelled/failed orders as "activity"; (2) the simulated A/B test's unit and metric were made logically consistent (checkout **attempts**, not "users", converting on **payment authorization**, not on an unrelated downstream return outcome); (3) the simulated Discovery Funnel's labeling was hardened so it can't be mistaken for measured behavior (stage names now say "(Simulated)", numbers are rounded to the nearest 50, and the real Order Fulfillment Funnel is now presented as the dashboard's primary funnel). All changes are described in the methodology sections below and were re-tested end-to-end (see [Testing Performed](#testing-performed)).

**➡️ Before anything else, read [What's Real vs. Derived vs. Simulated](#whats-real-vs-derived-vs-simulated) below.** This project is explicit about the difference, instead of presenting estimates as measurements.

---

## Table of Contents

- [What's Real vs. Derived vs. Simulated](#whats-real-vs-derived-vs-simulated)
- [Business & Product Questions](#business--product-questions)
- [Tech Stack](#tech-stack)
- [Architecture / Data Flow](#architecture--data-flow)
- [Database Schema](#database-schema)
- [Methodology](#methodology)
  - [Cohort Retention](#1-cohort-retention)
  - [Funnel Analysis](#2-funnel-analysis)
  - [A/B Testing](#3-ab-testing-simulated)
- [Genuine Insights From the Data](#genuine-insights-from-the-data)
- [Project Structure](#project-structure)
- [Setup & Exact Commands](#setup--exact-commands)
- [Running the Dashboard](#running-the-dashboard)
- [Testing Performed](#testing-performed)
- [Known Limitations](#known-limitations)
- [Original SQL Practice Set](#original-sql-practice-set)

---

## What's Real vs. Derived vs. Simulated

This dataset is a 9-table relational e-commerce schema (`customers`, `orders`, `order_items`, `products`, `category`, `sellers`, `payments`, `shippings`, `inventory`). It does **not** contain a signup-event table or a clickstream/event-tracking table. Rather than inventing that data, every analysis in this project is explicitly labeled:

| Analysis | Status | Why |
|---|---|---|
| Cohort retention | **Real analysis, derived acquisition proxy** | No signup date exists in `customers`; a customer's cohort month is defined as their *first successful order* month (a standard e-commerce proxy when no signup date is available). Both cohort assignment and monthly activity **exclude Cancelled orders** (`order_status = 'Cancelled'`, which correspond 1:1 to failed payments) — only orders where payment actually succeeded count as genuine customer activity. |
| Order Fulfillment Funnel (`funnel_fulfillment.csv`) — **primary funnel** | **100% real** | Built entirely from `orders.order_status`, `payments.payment_status`, and `shippings.delivery_status` — all real, internally consistent columns. This is the funnel featured first in the dashboard. |
| Discovery Funnel (`funnel_discovery_simulated.csv`) — secondary | **Simulated / illustrative** | This schema has no View/Cart/Checkout event table at all. Only the Purchase stage is real (anchored to the real completed-order count); View Item / Add to Cart / Checkout are estimated backwards from documented industry-average e-commerce conversion benchmarks, with a fixed random seed. Stage names are suffixed "(Simulated)" and values are rounded to the nearest 50 so they're never mistaken for exact measured counts. |
| A/B test (checkout flow) | **Fully simulated** | No experiment-assignment table exists in the schema, and no such test was run. The **unit** is a checkout attempt (not a "user"); the **metric** is payment authorization success — logically tied to what a checkout-flow change could plausibly affect. The control rate is the real payment-authorization rate (~97.74%); the treatment models a stated, assumed reduction in the failure rate. Fixed seed for reproducibility. |
| 19 original business-question queries | **100% real** | Straightforward SQL against the real schema (revenue, AOV, CLV, inventory, shipping, etc.) |

The dashboard repeats these labels inline (⚠️ warning banners on simulated sections, ✅ success banners on real sections) so nobody reading it mistakes a benchmark-based estimate for a measurement.

---

## Business & Product Questions

1. How well does the platform retain customers after their first purchase, and does retention decay over time or plateau?
2. Where in the order lifecycle do orders "leak" — payment failure, shipping, or returns — and what would a full top-of-funnel (browse → cart → checkout) picture plausibly look like?
3. If we shipped a new checkout flow, how would we know whether it actually improved conversion, and by how much confidence?
4. Which products, categories, sellers, and states actually drive revenue and profit, and where is risk (returns, low stock, inactive sellers) concentrated?

---

## Tech Stack

- **PostgreSQL 16** — schema, all analytical SQL (CTEs, window functions, generated columns, stored procedure)
- **Python 3** (`pandas`, `psycopg2`, `SQLAlchemy`) — data loading and SQL → CSV export pipeline
- **SciPy** (`scipy.stats`) — two-proportion z-test for the A/B test
- **Streamlit + Plotly** — interactive dashboard, deployable with zero database credentials

---

## Architecture / Data Flow

```
 data/raw/*.csv
        │
        ▼
 scripts/load_data.py   ──► PostgreSQL (schema from sql/01_schema.sql)
        │
        ▼
 sql/02_business_problems.sql   (19 business questions)
 sql/03_cohort_retention.sql    (real cohort analysis)
 sql/04_funnel_analysis.sql     (real order fulfillment funnel)
        │
        ▼
 scripts/export_analytics.py            ──► data/analytics_outputs/*.csv
 scripts/simulate_discovery_funnel.py    ──► funnel_discovery_simulated.csv
 scripts/ab_test_simulation.py           ──► ab_test_results.csv, ab_test_summary.csv
        │
        ▼
 dashboard/app.py (Streamlit + Plotly)
   reads ONLY from data/analytics_outputs/*.csv — no DB connection,
   no credentials, deployable to Streamlit Cloud as-is.
```

The dashboard is deliberately decoupled from PostgreSQL: **only** `load_data.py` and `export_analytics.py` touch the database, and they read credentials from environment variables (see `.env.example`). This keeps secrets out of the app that gets deployed publicly.

---

## Database Schema

9 tables: `category`, `customers`, `sellers`, `products`, `orders`, `order_items`, `payments`, `shippings`, `inventory`.

See `docs/erd_amazon.png` for the entity-relationship diagram and `sql/01_schema.sql` for the full DDL. Key facts about the real data (verified during the audit of this project, not assumed):

- 21,629 orders (2020-01-01 → 2024-07-30), 898 customers (686 of whom ever ordered), 765 products, 54 sellers, 6 categories.
- Every order has exactly one order line (`order_item_id == order_id` for all rows) — there are no true multi-item baskets in this dataset.
- `order_status`, `payment_status`, and `delivery_status` are perfectly cross-consistent: `Cancelled` ↔ `Payment Failed` ↔ no shipping record; `Inprogress` ↔ `Payment Successed` ↔ `Shipped`; `Completed` ↔ `Payment Successed` ↔ `Delivered`; `Returned` ↔ `Refunded` ↔ `Returned`.
- `customers` has no signup date column — see the cohort methodology below for how this is handled.
- `order_items.total_sale` is a `GENERATED ALWAYS AS (quantity * price_per_unit) STORED` column (an upgrade from the original schema's manual `UPDATE` statement) so it can never drift out of sync.

---

## Methodology

### 1. Cohort Retention

**File:** `sql/03_cohort_retention.sql` · **Output:** `cohort_retention.csv`, `cohort_retention_pivot.csv`

- `cohort_month` = the calendar month of a customer's first **successful** order — a `MIN(order_date) OVER (PARTITION BY customer_id)` **window function**, not a plain aggregate, computed inside a CTE (`successful_orders`) that already filters to successful orders, then rolled up in a second CTE (`customer_cohort`).
- **"Successful" means `order_status <> 'Cancelled'`.** Cancelled orders in this dataset correspond 1:1 to `payment_status = 'Payment Failed'` — the customer never actually completed a purchase, so counting a cancelled order as "activity" would overstate both acquisition and retention. Completed, Returned, and Inprogress orders are all counted (payment succeeded for all three at the time of purchase; a later return is a separate, post-purchase fulfillment outcome).
- `months_since_cohort` = integer number of months between a later active month and the cohort month.
- `retention_rate` = (customers with a successful order in that month-offset) ÷ (original cohort size) × 100.
- The pivoted CSV (`cohort_month` × `months_since_cohort` → `retention_rate`) feeds the Plotly heatmap directly. Pivoting is done in pandas rather than Postgres' `crosstab()`/`tablefunc` extension, so no extra Postgres extension needs to be enabled.
- **Impact of this filter:** 4 customers whose only order was ever cancelled are now correctly excluded from cohort membership entirely (682 customers now form cohorts, vs. 686 when cancelled orders were incorrectly counted as activity in an earlier pass of this project).

### 2. Funnel Analysis

**File:** `sql/04_funnel_analysis.sql` (real, **primary**) + `scripts/simulate_discovery_funnel.py` (simulated, secondary)

**Real — Order Fulfillment Funnel (primary funnel for this project):** `Orders Placed → Payment Successful → Delivered → Kept (Not Returned)`, built from `orders`, `payments`, and `shippings`. Every stage boundary was cross-checked against at least one other independent column in the schema (see the consistency table above) and matches exactly. This is the funnel shown first in the dashboard and the one that should be trusted for real decision-making.

**Simulated / illustrative — Discovery Funnel (secondary):** `View Item → Add to Cart → Checkout → Purchase`. This schema has no event/clickstream data, so this funnel cannot be measured — it exists only to sketch what a top-of-funnel view could plausibly look like. Only the `Purchase` stage is real (anchored to the real completed-order count, 17,802); the upper three stages are computed backwards using documented, industry-average e-commerce step-conversion benchmarks, with reproducible random noise (fixed seed = 42). To make sure this is never mistaken for real data: every stage name is suffixed `(Simulated)`, every estimate is rounded to the nearest 50 (a real measured count wouldn't round this cleanly), and every row carries `is_simulated = True` plus a `methodology` string. The real funnel's CSV also carries `is_simulated = False` on every row, so both files can be filtered/joined programmatically without relying on which file they came from.

### 3. A/B Testing (Simulated)

**File:** `scripts/ab_test_simulation.py` · **Output:** `ab_test_results.csv`, `ab_test_summary.csv`

A reproducible simulation of "new checkout flow" (Treatment, B) vs. "existing checkout flow" (Control, A), with the experimental design spelled out explicitly so unit and metric stay logically consistent:

| Element | Definition |
|---|---|
| **Experimental unit** | A single **checkout attempt** — one customer submitting their order/payment details. Not a "user", "customer", or "session"; the outcome is decided at that one submission, so the attempt is the unit of analysis. |
| **Conversion metric** | Binary: did that checkout attempt result in a **successfully authorized payment** (`order_status <> 'Cancelled'`)? This is chosen because a checkout-flow redesign plausibly affects payment errors and last-step drop-off — it has no plausible mechanism to affect an unrelated, much-later outcome like a product return. *(An earlier pass of this project used the return-adjusted "Kept (Not Returned)" rate as the baseline, which mixed checkout UX with a downstream fulfillment/product decision — that has been corrected here.)* |
| **Control (A)** | Existing checkout flow. Baseline rate = **97.74%**, the dataset's real payment-authorization rate (21,141 of 21,629 orders were not cancelled for payment failure) — used as-is, not invented. |
| **Treatment (B)** | Hypothetical new checkout flow, simulated to cut the **payment failure rate** by 25% relative (2.26% → 1.695%), rather than adding a flat lift to an already near-ceiling success rate (which would be implausible above ~97%). This is a stated hypothesis being tested, not a measured fact. |
| **Hypothesis** | H0: `p_treatment = p_control`. H1: `p_treatment ≠ p_control` (two-tailed). |

- Sample size: 10,000 simulated checkout attempts per arm — a plausible multi-week sample for a checkout test on a site this size (not derived from the dataset, since no session-level table exists to size a real test from; stated as an assumption, same as the effect size).
- Statistical test: **two-proportion z-test** (`scipy.stats.norm`), α = 0.05.
  - `z = (p̂_B − p̂_A) / SE_pooled`, using the pooled conversion rate across both arms.
  - Two-tailed p-value via the normal survival function (numerically stable for very small p-values, unlike `1 - cdf`, which saturates in floating point).
- **The winner is never hard-coded.** It's derived in code from `p_value < alpha` AND which arm has the higher observed rate — see `simulate_ab_test()` in `scripts/ab_test_simulation.py`.
- Fixed random seed (`42`) — the script produces byte-identical output on every run (verified, see [Testing Performed](#testing-performed)).
- Result with these assumptions: Control 97.60% vs. Treatment 98.50% (n=10,000/arm), z ≈ 4.60, p ≈ 4.2×10⁻⁶ — statistically significant, Treatment wins. This is a *simulated* result under the stated assumptions, not a real outcome.

---

## Genuine Insights From the Data

These come directly from the real schema (not simulated):

- **Revenue is heavily electronics-driven.** The `electronics` category alone accounts for **~89.7%** of total revenue ($11.34M of $12.64M) — every other category (Sports & Outdoors, Toys & Games, Pet Supplies, clothing, home & kitchen) combined is roughly 10%. A category-diversification review looks warranted.
- **Revenue is concentrated in a small number of high-value customers.** Order counts per customer range from 1 to 127, with a median of only 5 but a mean of ~31 — a small "power user" segment is doing disproportionate volume. Ohio customers (168 people) generated ~$6.87M, while Texas customers (just 50 people) generated ~$2.80M — nearly as much from a third of the customers.
- **~23.6% of registered customers have never placed an order** (212 of 898) — a concrete re-engagement/lifecycle-marketing target.
- **Cohort retention plateaus rather than decaying.** Among the 682 customers with at least one successful (non-cancelled) order, weighted average retention is ~34% at month 1 and stays essentially flat (~33–35%) all the way through month 12, instead of the classic steep decay curve. Combined with the power-user finding above, this suggests a bimodal customer base: a sizeable share of one-and-done buyers, and a loyal core that keeps ordering for years.
- **13.1% of all orders end in a return**, and the fulfillment funnel shows this is the single largest leak point after checkout (payment success is 97.7% and delivery is 95.4%, but only 82.3% of placed orders are ultimately kept) — returns, not payment or shipping failures, are where fulfilled revenue is actually lost. This is also why the A/B test above measures checkout-attempt payment success rather than the return-adjusted rate: returns are a separate problem with separate causes, several weeks downstream of checkout.

---

## Project Structure

```
AMAZON_PROJECT/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── docs/
│   └── erd_amazon.png
├── data/
│   ├── raw/                          # original source CSVs (unmodified)
│   │   ├── category.csv, customers.csv, sellers.csv, products.csv,
│   │   │   orders.csv, order_items.csv, payments.csv, shipping.csv,
│   │   │   inventory.csv
│   └── analytics_outputs/            # generated - dashboard reads only these
│       ├── kpi_summary.csv
│       ├── cohort_retention.csv
│       ├── cohort_retention_pivot.csv
│       ├── funnel_fulfillment.csv            (real)
│       ├── funnel_discovery_simulated.csv    (simulated)
│       ├── ab_test_results.csv               (simulated)
│       └── ab_test_summary.csv               (simulated)
├── sql/
│   ├── 01_schema.sql
│   ├── 02_business_problems.sql      # cleaned original 19-question set
│   ├── 03_cohort_retention.sql
│   └── 04_funnel_analysis.sql
├── scripts/
│   ├── load_data.py                  # CSV -> PostgreSQL
│   ├── export_analytics.py           # PostgreSQL -> CSV (only script + load_data.py that touch the DB)
│   ├── simulate_discovery_funnel.py  # simulated funnel
│   └── ab_test_simulation.py         # simulated A/B test
└── dashboard/
    └── app.py                        # Streamlit + Plotly, CSV-only, no DB
```

---

## Setup & Exact Commands

### Prerequisites
- PostgreSQL 12+ running locally (or any reachable instance)
- Python 3.9+

### 1. Clone and install dependencies
```bash
git clone <this-repo-url>
cd AMAZON_PROJECT
pip install -r requirements.txt
```

### 2. Configure database credentials
```bash
cp .env.example .env
# edit .env with your local PostgreSQL username/password
```

### 3. Create the database
```bash
createdb amazon_analytics
```

### 4. Load the schema and raw data
```bash
python scripts/load_data.py
```
This applies `sql/01_schema.sql` and bulk-loads all 9 CSVs from `data/raw/` in foreign-key-safe order, cleaning header/BOM inconsistencies along the way. It prints a row count per table and a sanity check on the generated `total_sale` column.

### 5. Run the analytical SQL and export CSVs
```bash
python scripts/export_analytics.py
python scripts/simulate_discovery_funnel.py
python scripts/ab_test_simulation.py
```

### 6. (Optional) Run the original 19-question business SQL directly
```bash
psql -d amazon_analytics -f sql/02_business_problems.sql
```

---

## Running the Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard reads **only** the CSVs produced in step 5 above — it never connects to PostgreSQL. This means:
- It can be deployed to **Streamlit Cloud** by pointing it at `dashboard/app.py`, with `data/analytics_outputs/*.csv` committed to the repo — no database secrets need to be configured on the hosting platform.
- If a CSV is missing, the affected dashboard section shows an informational message instead of crashing (verified — see below).

---

## Testing Performed

Everything below was actually executed against a live PostgreSQL 16 instance and a real Streamlit process while building this project (and again after the analytical QA pass), not just written and assumed to work:

**SQL**
- ✅ `sql/01_schema.sql` applied cleanly; all 9 tables + 10 indexes created.
- ✅ All 9 CSVs loaded via `load_data.py`: 21,629 orders, 21,629 order_items (0 with a NULL generated `total_sale`), 21,141 shippings, etc. — row counts match the source CSVs exactly.
- ✅ All 19 queries in `sql/02_business_problems.sql` executed with zero errors (one real bug found and fixed: a `ROUND()` call on a `double precision` value with no `::numeric` cast, which PostgreSQL rejects).
- ✅ The `add_sales` stored procedure was called end-to-end (`CALL add_sales(...)`) and verified to correctly insert into `orders`/`order_items` and decrement `inventory.stock`; a real copy-paste bug in the original procedure (it looked up price using `p_quantity` instead of `p_product_id`) was found and fixed. Test rows were deleted and inventory restored afterward (verified twice — once in the initial build, once again after the QA pass), so the delivered dataset is unmodified.
- ✅ Cohort SQL verified: retention at `months_since_cohort = 0` is exactly 100% for every cohort (sanity check for double counting/join errors).
- ✅ **QA pass:** re-verified that excluding `Cancelled` orders from the cohort SQL correctly drops exactly 4 customers (686 → 682) whose only order was ever cancelled, and that the window-function-based cohort assignment (`MIN(order_date) OVER (PARTITION BY customer_id)`) produces identical cohort months to the original `GROUP BY` approach for every retained customer.
- ✅ Funnel SQL verified: every stage's drop-off count reconciles exactly against the independent `order_status` distribution (e.g. the Payment Successful → Delivered drop-off of 499 matches the `Inprogress` order count exactly).

**Python**
- ✅ `ab_test_simulation.py` runs end-to-end with `scipy.stats`; two consecutive runs produce byte-identical output (`diff` confirmed), verifying the fixed seed makes it fully reproducible.
- ✅ The winner field was confirmed to come from code logic, not a literal — traced through `simulate_ab_test()`.
- ✅ **QA pass:** re-verified the corrected experiment design — control rate is read directly from the real 97.74% payment-authorization rate (not hard-coded as a rounded literal), and the treatment rate is derived via the failure-rate-reduction formula rather than a flat percentage lift, confirmed by inspecting the computed `p_treatment` (98.31%) against the formula in the docstring.
- ✅ `simulate_discovery_funnel.py` correctly anchors its `Purchase` stage to the real value read from `funnel_fulfillment.csv`, and the rounding-to-nearest-50 behavior was verified on the output (all four `estimated_users` values end in `00` or `50`).

**Streamlit**
- ✅ Dashboard script passes Streamlit's official `AppTest` harness with **zero exceptions**, all section headers rendering, and 12 KPI/result metrics populating with correct values — re-verified after every methodology change in the QA pass.
- ✅ Verified the dashboard process serves HTTP 200 and a passing `/_stcore/health` check with **no PostgreSQL connection active** — confirming the "no live DB connection" requirement.
- ✅ Missing-file resilience tested directly (twice — before and after the QA pass): with `data/analytics_outputs/` emptied, the app still runs with zero exceptions and shows an informational message per missing section instead of crashing.
- ✅ **QA pass:** confirmed the Discovery Funnel tab reads the renamed `estimated_users` column (not the old `users` column) without error, and that the A/B test section reads the renamed `checkout_attempts`/`successful_checkouts` columns correctly.
- ✅ **Full clean-clone re-run after the QA pass:** dropped and recreated the database, then re-ran `load_data.py → export_analytics.py → simulate_discovery_funnel.py → ab_test_simulation.py → sql/02_business_problems.sql` back-to-back from scratch — all steps completed with zero errors and identical row counts to the original build.

---

## Known Limitations

- **No clickstream data exists in this schema.** The Discovery Funnel is a labeled simulation/illustration, not a measurement — see [What's Real vs. Derived vs. Simulated](#whats-real-vs-derived-vs-simulated).
- **No experiment-assignment table exists.** The A/B test is a full simulation for demonstration of methodology, not a real Amazon experiment. Sample sizes (10,000 checkout attempts/arm) and the assumed effect size (25% relative failure-rate reduction) are stated assumptions, not derived from data.
- **No customer signup date exists.** Cohort "acquisition" uses first-successful-order month as a proxy, which slightly understates true time-to-first-purchase for customers who browsed/registered before their first order (that gap isn't observable in this schema).
- **Every order has exactly one line item** in this dataset — there's no true multi-item-basket behavior to analyze (e.g. basket-size or cross-sell metrics wouldn't be meaningful here).
- Cohort sizes shrink sharply for recent months (as few as 1 customer in some 2023–2024 cohorts), so month-over-month retention swings a lot in the more recent cohorts purely from small-sample noise — visible directly in the heatmap.

---

## Original SQL Practice Set

The 19 original business-question queries (top products, revenue by category, AOV, CLV, inventory alerts, shipping delays, payment success rate, seller performance, profit margin, return rate, inactive sellers, customer segmentation, YoY decline, and the `add_sales` stored procedure) are preserved and cleaned up in `sql/02_business_problems.sql`, with two real bugs fixed along the way (documented inline in that file and in Testing Performed above).
