-- =============================================================================
-- AMAZON E-COMMERCE PRODUCT ANALYTICS PROJECT
-- 01_schema.sql
--
-- Defines the relational schema. This is the same 9-table design as the
-- original project (see docs/erd_amazon.png), with two small, deliberate
-- upgrades:
--   1. order_items.total_sale is a STORED GENERATED COLUMN instead of a
--      manual UPDATE step, so it can never drift out of sync with
--      quantity * price_per_unit.
--   2. Indexes were added on foreign keys and on columns that the analytics
--      queries filter/group/join on (order_date, customer_id, order_id,
--      product_id, order_status). The raw CSVs are small enough that this
--      isn't strictly required for correctness, but it reflects how a
--      production analytics schema on these tables would actually be built.
-- No columns, tables, or relationships were invented — this mirrors the
-- original schemas.sql exactly in structure.
-- =============================================================================

DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS shippings CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS inventory CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS sellers CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS category CASCADE;

-- ---------------------------------------------------------------------------
-- category
-- ---------------------------------------------------------------------------
CREATE TABLE category (
    category_id   INT PRIMARY KEY,
    category_name VARCHAR(20)
);

-- ---------------------------------------------------------------------------
-- customers
-- Note: there is no signup/registration date in the source data. The only
-- attributes available are name and state. Any "acquisition date" used
-- later in this project (cohort analysis) is a derived proxy based on each
-- customer's first order date, not a real signup event.
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    first_name  VARCHAR(20),
    last_name   VARCHAR(20),
    state       VARCHAR(20),
    address     VARCHAR(5) DEFAULT ('xxxx')
);

-- ---------------------------------------------------------------------------
-- sellers
-- ---------------------------------------------------------------------------
CREATE TABLE sellers (
    seller_id   INT PRIMARY KEY,
    seller_name VARCHAR(25),
    origin      VARCHAR(10)
);

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
CREATE TABLE products (
    product_id   INT PRIMARY KEY,
    product_name VARCHAR(60),
    price        FLOAT,
    cogs         FLOAT,
    category_id  INT,
    CONSTRAINT product_fk_category FOREIGN KEY (category_id) REFERENCES category(category_id)
);

-- ---------------------------------------------------------------------------
-- orders
-- order_status observed in the data: Completed, Returned, Inprogress, Cancelled
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    order_id     INT PRIMARY KEY,
    order_date   DATE,
    customer_id  INT,
    seller_id    INT,
    order_status VARCHAR(15),
    CONSTRAINT orders_fk_customers FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT orders_fk_sellers   FOREIGN KEY (seller_id)   REFERENCES sellers(seller_id)
);

-- ---------------------------------------------------------------------------
-- order_items
-- In this dataset every order has exactly one order_item row
-- (order_item_id == order_id for all 21,629 rows). total_sale is generated,
-- not stored/updated manually, so it's always consistent.
-- ---------------------------------------------------------------------------
CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY,
    order_id      INT,
    product_id    INT,
    quantity      INT,
    price_per_unit FLOAT,
    total_sale    FLOAT GENERATED ALWAYS AS (quantity * price_per_unit) STORED,
    CONSTRAINT order_items_fk_orders   FOREIGN KEY (order_id)   REFERENCES orders(order_id),
    CONSTRAINT order_items_fk_products FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- ---------------------------------------------------------------------------
-- payments
-- payment_status observed: Payment Successed, Refunded, Payment Failed
-- ---------------------------------------------------------------------------
CREATE TABLE payments (
    payment_id     INT PRIMARY KEY,
    order_id       INT,
    payment_date   DATE,
    payment_status VARCHAR(20),
    CONSTRAINT payments_fk_orders FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- ---------------------------------------------------------------------------
-- shippings
-- delivery_status observed: Delivered, Returned, Shipped
-- Note: orders with order_status = 'Cancelled' have NO row here (they never
-- shipped) - this is a genuine, consistent pattern in the source data, not
-- a data quality issue.
-- ---------------------------------------------------------------------------
CREATE TABLE shippings (
    shipping_id        INT PRIMARY KEY,
    order_id            INT,
    shipping_date       DATE,
    return_date         DATE,
    shipping_providers  VARCHAR(50),
    delivery_status     VARCHAR(50),
    CONSTRAINT shippings_fk_orders FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- ---------------------------------------------------------------------------
-- inventory
-- ---------------------------------------------------------------------------
CREATE TABLE inventory (
    inventory_id    INT PRIMARY KEY,
    product_id      INT,
    stock           INT,
    warehouse_id    INT,
    last_stock_date DATE,
    CONSTRAINT inventory_fk_products FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- ---------------------------------------------------------------------------
-- Indexes to support the analytics workload (joins/filters/group-bys used
-- throughout sql/02, sql/03, sql/04)
-- ---------------------------------------------------------------------------
CREATE INDEX idx_orders_customer_id   ON orders(customer_id);
CREATE INDEX idx_orders_seller_id     ON orders(seller_id);
CREATE INDEX idx_orders_order_date    ON orders(order_date);
CREATE INDEX idx_orders_order_status  ON orders(order_status);
CREATE INDEX idx_order_items_order_id   ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
CREATE INDEX idx_payments_order_id    ON payments(order_id);
CREATE INDEX idx_shippings_order_id   ON shippings(order_id);
CREATE INDEX idx_products_category_id ON products(category_id);
CREATE INDEX idx_inventory_product_id ON inventory(product_id);

-- end of schema
