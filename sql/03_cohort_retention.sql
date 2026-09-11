-- =============================================================================
-- 03_cohort_retention.sql
--
-- Monthly cohort retention analysis.
--
-- METHODOLOGY NOTES:
--
-- 1) Acquisition proxy (documented, unchanged from v1):
--    The `customers` table has no signup/registration date column - only
--    name and state. There is no independent "acquisition event" in this
--    schema. Following standard e-commerce cohort-analysis practice when no
--    signup date exists, a customer's cohort month is defined as the
--    calendar month of their FIRST SUCCESSFUL ORDER.
--
-- 2) "Successful" activity definition (fixed in this pass):
--    Both cohort assignment AND monthly activity are now restricted to
--    orders where order_status <> 'Cancelled'. Cancelled orders in this
--    dataset correspond 1:1 to payment_status = 'Payment Failed' (see
--    sql/04_funnel_analysis.sql's consistency table) - the customer never
--    actually completed a purchase, so counting a cancelled order as
--    "activity" would overstate acquisition and retention. Completed,
--    Returned, and Inprogress orders all represent a payment that DID
--    succeed at the time of purchase, so they are all counted as genuine
--    customer activity. (A later return is a fulfillment/product outcome,
--    not evidence the purchase itself didn't happen.)
--
-- 3) Window function (added in this pass):
--    Cohort assignment now uses MIN(order_date) OVER (PARTITION BY
--    customer_id) - a genuine window function - instead of a plain
--    GROUP BY aggregate, and is combined with CTEs throughout.
--
-- Output columns (matches the required shape for the Plotly heatmap):
--   cohort_month, months_since_cohort, cohort_size, retained_users, retention_rate
-- =============================================================================

WITH successful_orders AS (
    -- Only orders that actually represent completed payment activity.
    -- Cancelled ('Payment Failed') orders are excluded from both cohort
    -- assignment and monthly activity.
    SELECT
        customer_id,
        order_id,
        order_date,
        DATE_TRUNC('month', order_date)::date AS activity_month,
        -- window function: each customer's first successful order date,
        -- computed without collapsing the row set (so order_id/order_date
        -- stay available if needed for QA)
        MIN(order_date) OVER (PARTITION BY customer_id) AS first_order_date
    FROM orders
    WHERE order_status <> 'Cancelled'
),

customer_cohort AS (
    SELECT DISTINCT
        customer_id,
        DATE_TRUNC('month', first_order_date)::date AS cohort_month
    FROM successful_orders
),

customer_activity AS (
    SELECT DISTINCT
        customer_id,
        activity_month
    FROM successful_orders
),

cohort_activity AS (
    SELECT
        cc.cohort_month,
        ca.activity_month,
        ca.customer_id,
        (
            (EXTRACT(YEAR  FROM ca.activity_month) - EXTRACT(YEAR  FROM cc.cohort_month)) * 12
          + (EXTRACT(MONTH FROM ca.activity_month) - EXTRACT(MONTH FROM cc.cohort_month))
        )::int AS months_since_cohort
    FROM customer_activity AS ca
    JOIN customer_cohort AS cc ON cc.customer_id = ca.customer_id
),

cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM customer_cohort
    GROUP BY cohort_month
),

retention AS (
    SELECT
        cohort_month,
        months_since_cohort,
        COUNT(DISTINCT customer_id) AS retained_users
    FROM cohort_activity
    GROUP BY 1, 2
)

SELECT
    r.cohort_month,
    r.months_since_cohort,
    cs.cohort_size,
    r.retained_users,
    ROUND((r.retained_users::numeric / cs.cohort_size::numeric) * 100, 2) AS retention_rate
FROM retention AS r
JOIN cohort_sizes AS cs ON cs.cohort_month = r.cohort_month
ORDER BY r.cohort_month, r.months_since_cohort;
