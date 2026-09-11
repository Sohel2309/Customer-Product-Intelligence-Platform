-- =============================================================================
-- 04_funnel_analysis.sql
--
-- REAL, data-driven funnel: "Order Fulfillment & Retention Funnel"
--
-- IMPORTANT - this is NOT the classic e-commerce clickstream funnel
-- (View Item -> Add to Cart -> Checkout -> Purchase). This schema has NO
-- clickstream/event tracking table of any kind - there is no page-view,
-- cart, or checkout-initiation data anywhere in the source project. Rather
-- than fabricate that data, this file builds the strongest funnel the
-- ACTUAL schema supports: the order's real lifecycle, cross-checked across
-- three independent tables (orders.order_status, payments.payment_status,
-- shippings.delivery_status), which turn out to be perfectly consistent
-- with each other in this dataset:
--
--   order_status | payment_status     | delivery_status | shipping row?
--   -------------|--------------------|-----------------|--------------
--   Cancelled    | Payment Failed     | (none)          | no
--   Inprogress   | Payment Successed  | Shipped         | yes
--   Completed    | Payment Successed  | Delivered       | yes
--   Returned     | Refunded           | Returned        | yes
--
-- Stages (each stage is a strict subset of orders that reached it):
--   1. Orders Placed        -> every order in the orders table
--   2. Payment Successful   -> order_status <> 'Cancelled'
--   3. Delivered            -> order reached the customer (Completed or Returned)
--   4. Kept (Not Returned)  -> order_status = 'Completed'
--
-- A second, clearly SIMULATED "Product Discovery Funnel" (View -> Cart ->
-- Checkout -> Purchase) is generated separately in
-- scripts/simulate_discovery_funnel.py, anchored to the real "Kept" count
-- from this query, since that data genuinely does not exist here and must
-- not be presented as if it were measured.
-- =============================================================================

WITH funnel_base AS (
    SELECT
        o.order_id,
        o.order_status,
        CASE WHEN o.order_status <> 'Cancelled' THEN 1 ELSE 0 END AS reached_payment,
        CASE WHEN o.order_status IN ('Completed', 'Returned') THEN 1 ELSE 0 END AS reached_delivered,
        CASE WHEN o.order_status = 'Completed' THEN 1 ELSE 0 END AS reached_kept
    FROM orders AS o
),
stage_counts AS (
    SELECT
        COUNT(DISTINCT order_id) AS orders_placed,
        SUM(reached_payment)     AS payment_successful,
        SUM(reached_delivered)   AS delivered,
        SUM(reached_kept)        AS kept_not_returned
    FROM funnel_base
)
SELECT stage, stage_order, users AS orders, drop_off, conversion_from_previous_pct,
       conversion_from_start_pct, is_simulated
FROM (
    SELECT
        1 AS stage_order, 'Orders Placed' AS stage,
        orders_placed AS users,
        NULL::int AS drop_off,
        NULL::numeric AS conversion_from_previous_pct,
        100.00::numeric AS conversion_from_start_pct,
        FALSE AS is_simulated
    FROM stage_counts
    UNION ALL
    SELECT
        2, 'Payment Successful',
        payment_successful,
        orders_placed - payment_successful,
        ROUND(payment_successful::numeric / orders_placed::numeric * 100, 2),
        ROUND(payment_successful::numeric / orders_placed::numeric * 100, 2),
        FALSE
    FROM stage_counts
    UNION ALL
    SELECT
        3, 'Delivered',
        delivered,
        payment_successful - delivered,
        ROUND(delivered::numeric / payment_successful::numeric * 100, 2),
        ROUND(delivered::numeric / orders_placed::numeric * 100, 2),
        FALSE
    FROM stage_counts
    UNION ALL
    SELECT
        4, 'Kept (Not Returned)',
        kept_not_returned,
        delivered - kept_not_returned,
        ROUND(kept_not_returned::numeric / delivered::numeric * 100, 2),
        ROUND(kept_not_returned::numeric / orders_placed::numeric * 100, 2),
        FALSE
    FROM stage_counts
) AS funnel
ORDER BY stage_order;
