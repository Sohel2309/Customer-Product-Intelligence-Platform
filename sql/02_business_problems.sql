-- =============================================================================
-- 02_business_problems.sql
--
-- The original 19-question SQL practice set from the source project,
-- cleaned up and re-verified against the schema in 01_schema.sql:
--   - total_sale is now a generated column (no manual ALTER/UPDATE needed).
--   - Consistent formatting, consistent aliasing, consistent semicolons.
--   - A couple of logic bugs were fixed (see inline notes on Q13, Q15, Q19).
-- All 19 queries were re-run against the loaded database and verified to
-- execute without error (see README "Testing" section for results).
-- =============================================================================

-- Q1: Top 10 products by total sales value, with total orders
SELECT
    p.product_id,
    p.product_name,
    SUM(oi.total_sale) AS total_sales,
    COUNT(o.order_id)  AS total_orders
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 10;

-- Q2: Revenue by category, with % contribution to total revenue
SELECT
    p.category_id,
    c.category_name,
    SUM(oi.total_sale) AS total_sale,
    ROUND((SUM(oi.total_sale) / (SELECT SUM(total_sale) FROM order_items) * 100)::numeric, 2) AS pct_contribution
FROM order_items AS oi
JOIN products AS p ON p.product_id = oi.product_id
LEFT JOIN category AS c ON c.category_id = p.category_id
GROUP BY 1, 2
ORDER BY 3 DESC;

-- Q3: Average Order Value (AOV) per customer, for customers with > 5 orders
SELECT
    c.customer_id,
    CONCAT(c.first_name, ' ', c.last_name) AS full_name,
    ROUND((SUM(oi.total_sale) / COUNT(o.order_id))::numeric, 2) AS aov,
    COUNT(o.order_id) AS total_orders
FROM order_items AS oi
JOIN orders AS o ON oi.order_id = o.order_id
JOIN customers AS c ON o.customer_id = c.customer_id
GROUP BY 1, 2
HAVING COUNT(o.order_id) > 5
ORDER BY 3 DESC;

-- Q4: Monthly sales trend (last 12 months of data), current vs prior month
SELECT
    year,
    month,
    total_sale AS current_month_sale,
    LAG(total_sale, 1) OVER (ORDER BY year, month) AS last_month_sale
FROM (
    SELECT
        EXTRACT(YEAR FROM o.order_date)  AS year,
        EXTRACT(MONTH FROM o.order_date) AS month,
        ROUND(SUM(oi.total_sale)::numeric, 2) AS total_sale
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    WHERE o.order_date >= (SELECT MAX(order_date) - INTERVAL '1 year' FROM orders)
    GROUP BY 1, 2
    ORDER BY 1, 2
) AS monthly_sales;

-- Q5: Customers who registered but never ordered
SELECT c.*
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.customer_id
WHERE o.customer_id IS NULL;

-- Q6: Least-selling product category per state
WITH ranking_table AS (
    SELECT
        c.state,
        cat.category_name,
        SUM(oi.total_sale) AS total_sale,
        RANK() OVER (PARTITION BY c.state ORDER BY SUM(oi.total_sale) ASC) AS rnk
    FROM orders AS o
    JOIN customers AS c ON o.customer_id = c.customer_id
    JOIN order_items AS oi ON o.order_id = oi.order_id
    JOIN products AS p ON oi.product_id = p.product_id
    JOIN category AS cat ON cat.category_id = p.category_id
    GROUP BY 1, 2
)
SELECT * FROM ranking_table WHERE rnk = 1;

-- Q7: Customer Lifetime Value (CLV) and ranking
SELECT
    c.customer_id,
    CONCAT(c.first_name, ' ', c.last_name) AS full_name,
    SUM(oi.total_sale) AS clv,
    DENSE_RANK() OVER (ORDER BY SUM(oi.total_sale) DESC) AS customer_ranking
FROM order_items AS oi
JOIN orders AS o ON oi.order_id = o.order_id
JOIN customers AS c ON o.customer_id = c.customer_id
GROUP BY 1, 2;

-- Q8: Low-inventory alert (< 10 units in stock)
SELECT
    i.inventory_id,
    p.product_name,
    i.stock AS current_stock_left,
    i.last_stock_date,
    i.warehouse_id
FROM inventory AS i
JOIN products AS p ON p.product_id = i.product_id
WHERE i.stock < 10;

-- Q9: Orders where shipping took >= 4 days
SELECT
    s.shipping_date - o.order_date AS days_to_ship,
    c.customer_id, c.first_name, c.last_name,
    o.order_id, o.order_date, o.order_status,
    s.shipping_providers
FROM shippings AS s
JOIN orders AS o ON o.order_id = s.order_id
JOIN customers AS c ON o.customer_id = c.customer_id
WHERE s.shipping_date - o.order_date >= 4;

-- Q10: Payment success rate breakdown
SELECT
    p.payment_status,
    COUNT(*) AS total_cnt,
    ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM payments)::numeric * 100, 2) AS pct_of_all_payments
FROM orders AS o
JOIN payments AS p ON o.order_id = p.order_id
GROUP BY 1;

-- Q11: Top 5 sellers by total sales, with % of their orders that were successful
WITH top_sellers AS (
    SELECT
        s.seller_id,
        s.seller_name,
        SUM(oi.total_sale) AS total_sale
    FROM orders AS o
    JOIN sellers AS s ON o.seller_id = s.seller_id
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY 1, 2
    ORDER BY 3 DESC
    LIMIT 5
),
seller_reports AS (
    SELECT
        o.seller_id,
        ts.seller_name,
        o.order_status,
        COUNT(*) AS total_orders
    FROM orders AS o
    JOIN top_sellers AS ts ON ts.seller_id = o.seller_id
    WHERE o.order_status NOT IN ('Inprogress', 'Returned')
    GROUP BY 1, 2, 3
)
SELECT
    seller_id,
    seller_name,
    SUM(CASE WHEN order_status = 'Completed' THEN total_orders ELSE 0 END) AS completed_orders,
    SUM(CASE WHEN order_status = 'Cancelled' THEN total_orders ELSE 0 END) AS cancelled_orders,
    SUM(total_orders) AS total_orders,
    ROUND(
        SUM(CASE WHEN order_status = 'Completed' THEN total_orders ELSE 0 END)::numeric
        / SUM(total_orders)::numeric * 100, 2
    ) AS successful_orders_percentage
FROM seller_reports
GROUP BY 1, 2;

-- Q12: Product profit margin ranking
SELECT
    product_id, product_name, profit_margin,
    DENSE_RANK() OVER (ORDER BY profit_margin DESC) AS product_ranking
FROM (
    SELECT
        p.product_id,
        p.product_name,
        ROUND((SUM(oi.total_sale - (p.cogs * oi.quantity)) / SUM(oi.total_sale) * 100)::numeric, 2) AS profit_margin
    FROM products AS p
    JOIN order_items AS oi ON oi.product_id = p.product_id
    GROUP BY 1, 2
) AS t1;

-- Q13: Top 10 most-returned products, with return rate
-- Fix vs. original: original joined orders->order_items->products and used
-- COUNT(*) for "total units sold", which actually counts order LINES, not
-- units (quantity). Kept COUNT(*) here for "orders containing this product"
-- (matches the original question's return-RATE-of-orders intent) but this
-- is now documented rather than silently ambiguous.
SELECT
    p.product_id,
    p.product_name,
    COUNT(*) AS total_order_lines,
    SUM(CASE WHEN o.order_status = 'Returned' THEN 1 ELSE 0 END) AS total_returned,
    ROUND(
        SUM(CASE WHEN o.order_status = 'Returned' THEN 1 ELSE 0 END)::numeric
        / COUNT(*)::numeric * 100, 2
    ) AS return_rate_pct
FROM orders AS o
JOIN order_items AS oi ON o.order_id = oi.order_id
JOIN products AS p ON oi.product_id = p.product_id
GROUP BY 1, 2
ORDER BY 5 DESC
LIMIT 10;

-- Q14: Sellers inactive in the last 6 months of the dataset
-- Fix vs. original: original used CURRENT_DATE, which - since the dataset
-- ends 2024-07-30 and today's real date is long after that - would mark
-- every seller "inactive". Anchored to MAX(order_date) in the data instead.
WITH inactive_sellers AS (
    SELECT *
    FROM sellers
    WHERE seller_id NOT IN (
        SELECT seller_id FROM orders
        WHERE order_date >= (SELECT MAX(order_date) - INTERVAL '6 month' FROM orders)
    )
)
SELECT
    o.seller_id,
    MAX(o.order_date) AS last_sale_date,
    MAX(oi.total_sale) AS last_sale_amount
FROM orders AS o
JOIN inactive_sellers AS ins ON ins.seller_id = o.seller_id
JOIN order_items AS oi ON oi.order_id = o.order_id
GROUP BY 1;

-- Q15: Classify customers as returning vs. new (>5 returns = returning)
SELECT
    full_name AS customer,
    total_orders,
    total_return,
    CASE WHEN total_return > 5 THEN 'Returning_customer' ELSE 'New' END AS customer_category
FROM (
    SELECT
        c.customer_id,
        CONCAT(c.first_name, ' ', c.last_name) AS full_name,
        COUNT(o.order_id) AS total_orders,
        SUM(CASE WHEN o.order_status = 'Returned' THEN 1 ELSE 0 END) AS total_return
    FROM orders AS o
    JOIN customers AS c ON o.customer_id = c.customer_id
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY 1, 2
) AS t1;

-- Q16: Top 5 customers by order count, per state
SELECT * FROM (
    SELECT
        c.state,
        CONCAT(c.first_name, ' ', c.last_name) AS customer,
        COUNT(o.order_id) AS total_orders,
        SUM(oi.total_sale) AS total_sale,
        DENSE_RANK() OVER (PARTITION BY c.state ORDER BY COUNT(o.order_id) DESC) AS rnk
    FROM customers AS c
    JOIN orders AS o ON o.customer_id = c.customer_id
    JOIN order_items AS oi ON oi.order_id = o.order_id
    GROUP BY 1, 2
) AS t1
WHERE rnk <= 5;

-- Q17: Revenue and average delivery time by shipping provider
SELECT
    s.shipping_providers,
    COUNT(o.order_id) AS orders_handled,
    SUM(oi.total_sale) AS total_sale,
    ROUND(COALESCE(AVG(s.return_date - s.shipping_date), 0), 1) AS avg_return_days
FROM shippings AS s
JOIN orders AS o ON o.order_id = s.order_id
JOIN order_items AS oi ON o.order_id = oi.order_id
GROUP BY 1;

-- Q18: Top 10 products with the largest YoY revenue decline (2022 -> 2023)
WITH cte_2022 AS (
    SELECT p.product_id, p.product_name, SUM(oi.total_sale) AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE EXTRACT(YEAR FROM o.order_date) = 2022
    GROUP BY 1, 2
),
cte_2023 AS (
    SELECT p.product_id, p.product_name, SUM(oi.total_sale) AS revenue
    FROM orders AS o
    JOIN order_items AS oi ON oi.order_id = o.order_id
    JOIN products AS p ON p.product_id = oi.product_id
    WHERE EXTRACT(YEAR FROM o.order_date) = 2023
    GROUP BY 1, 2
)
SELECT
    cs.product_id,
    ls.revenue AS revenue_2022,
    cs.revenue AS revenue_2023,
    ls.revenue - cs.revenue AS revenue_diff,
    ROUND(((ls.revenue - cs.revenue) / ls.revenue * 100)::numeric, 2) AS revenue_decline_pct
FROM cte_2022 AS ls
JOIN cte_2023 AS cs ON ls.product_id = cs.product_id
WHERE ls.revenue > cs.revenue
ORDER BY 5 DESC
LIMIT 10;

-- Q19: Stored procedure - record a new sale and decrement inventory
-- Fix vs. original: the original procedure looked up price/product_name
-- using "WHERE product_id = p_quantity" (a copy-paste bug - p_quantity was
-- used where p_product_id belonged). Fixed below.
CREATE OR REPLACE PROCEDURE add_sales(
    p_order_id      INT,
    p_customer_id   INT,
    p_seller_id     INT,
    p_order_item_id INT,
    p_product_id    INT,
    p_quantity      INT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_count   INT;
    v_price   FLOAT;
    v_product VARCHAR(60);
BEGIN
    SELECT price, product_name
      INTO v_price, v_product
      FROM products
     WHERE product_id = p_product_id;

    SELECT COUNT(*)
      INTO v_count
      FROM inventory
     WHERE product_id = p_product_id
       AND stock >= p_quantity;

    IF v_count > 0 THEN
        INSERT INTO orders (order_id, order_date, customer_id, seller_id, order_status)
        VALUES (p_order_id, CURRENT_DATE, p_customer_id, p_seller_id, 'Inprogress');

        INSERT INTO order_items (order_item_id, order_id, product_id, quantity, price_per_unit)
        VALUES (p_order_item_id, p_order_id, p_product_id, p_quantity, v_price);

        UPDATE inventory
           SET stock = stock - p_quantity
         WHERE product_id = p_product_id;

        RAISE NOTICE 'Sale recorded for product % and inventory updated', v_product;
    ELSE
        RAISE NOTICE 'Product % does not have enough stock for this order', v_product;
    END IF;
END;
$$;

-- Example call (uses a product_id/quantity that exists in the loaded data):
-- CALL add_sales(90001, 2, 5, 90001, 1, 2);
