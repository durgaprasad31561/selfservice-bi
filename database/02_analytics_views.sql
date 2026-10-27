-- =====================================================================
-- 02_analytics_views.sql — business model at the correct grain (schema "analytics")
--
-- Built as tables (CREATE TABLE AS) so they can carry primary keys and
-- indexes; the loader rebuilds them after every raw load.
--
-- Grain rules (prevents double counting):
--   fact_orders       1 row per order   — payments and items are pre-aggregated
--                                         separately per order, never joined row-to-row
--   fact_order_items  1 row per order item
--   fact_payments     1 row per payment
--
-- Business rules (e.g. which statuses count as revenue) live in the semantic
-- layer (backend/app/semantic/model.yaml), NOT here. These tables only hold
-- cleaned facts and descriptive attributes.
-- =====================================================================

DROP TABLE IF EXISTS
    analytics.meta_data_coverage, analytics.dim_date, analytics.dim_geo,
    analytics.dim_customers, analytics.dim_products, analytics.dim_sellers,
    analytics.dim_states, analytics.fact_payments, analytics.fact_order_items,
    analytics.fact_orders
CASCADE;

-- ---------------------------------------------------------------------
-- dim_states
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_states AS
SELECT state_code, state_name, region
FROM raw.states;
ALTER TABLE analytics.dim_states ADD PRIMARY KEY (state_code);

-- ---------------------------------------------------------------------
-- fact_orders — 1 row per order
-- ---------------------------------------------------------------------
CREATE TABLE analytics.fact_orders AS
WITH pay AS (
    SELECT order_id,
           SUM(payment_value)        AS order_revenue,
           MAX(payment_installments) AS installments,
           COUNT(*)                  AS payment_count
    FROM raw.payments
    GROUP BY order_id
),
pay_primary AS (
    -- the payment type that paid the largest share of the order
    SELECT DISTINCT ON (order_id) order_id, payment_type
    FROM raw.payments
    ORDER BY order_id, payment_value DESC, payment_sequential
),
items AS (
    SELECT order_id,
           SUM(price)                AS items_amount,
           SUM(freight_value)        AS freight_amount,
           COUNT(*)                  AS item_count,
           COUNT(DISTINCT seller_id) AS seller_count
    FROM raw.order_items
    GROUP BY order_id
),
rev AS (
    SELECT order_id,
           AVG(review_score) AS review_score,
           COUNT(*)          AS review_count
    FROM raw.reviews
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    COUNT(*) OVER (PARTITION BY c.customer_unique_id)::int AS customer_lifetime_orders,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,
    s.state_name                                         AS customer_state_name,
    s.region                                             AS customer_region,
    o.order_status,
    o.order_purchase_timestamp                           AS purchase_timestamp,
    o.order_purchase_timestamp::date                     AS purchase_date,
    date_trunc('month', o.order_purchase_timestamp)::date AS purchase_month,
    EXTRACT(YEAR FROM o.order_purchase_timestamp)::int   AS purchase_year,
    COALESCE(p.order_revenue, 0)::numeric(12,2)          AS order_revenue,
    COALESCE(i.items_amount, 0)::numeric(12,2)           AS items_amount,
    COALESCE(i.freight_amount, 0)::numeric(12,2)         AS freight_amount,
    COALESCE(i.item_count, 0)::int                       AS item_count,
    COALESCE(i.seller_count, 0)::int                     AS seller_count,
    pp.payment_type                                      AS primary_payment_type,
    CASE pp.payment_type
        WHEN 'credit_card' THEN 'Credit Card'
        WHEN 'boleto'      THEN 'Boleto'
        WHEN 'voucher'     THEN 'Voucher'
        WHEN 'debit_card'  THEN 'Debit Card'
        WHEN 'not_defined' THEN 'Not Defined'
    END                                                  AS primary_payment_type_label,
    p.installments::int                                  AS installments,
    COALESCE(p.payment_count, 0)::int                    AS payment_count,
    o.order_approved_at                                  AS approved_at,
    o.order_delivered_carrier_date                       AS carrier_date,
    o.order_delivered_customer_date                      AS delivered_date,
    o.order_estimated_delivery_date                      AS estimated_date,
    ROUND(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp))
          / 86400.0, 2)::numeric(8,2)                    AS delivery_days,
    CASE WHEN o.order_delivered_customer_date IS NULL OR o.order_estimated_delivery_date IS NULL
         THEN NULL
         ELSE o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date
    END                                                  AS is_late,
    CASE WHEN o.order_delivered_customer_date IS NULL OR o.order_estimated_delivery_date IS NULL
         THEN NULL
         WHEN o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date
         THEN 'Late'
         ELSE 'On Time'
    END                                                  AS delivery_status,
    ROUND(r.review_score, 2)::numeric(3,2)               AS review_score,
    COALESCE(r.review_count, 0)::int                     AS review_count
FROM raw.orders o
JOIN raw.customers c   ON c.customer_id = o.customer_id
JOIN raw.states s      ON s.state_code = c.customer_state
LEFT JOIN pay p        ON p.order_id = o.order_id
LEFT JOIN pay_primary pp ON pp.order_id = o.order_id
LEFT JOIN items i      ON i.order_id = o.order_id
LEFT JOIN rev r        ON r.order_id = o.order_id;

ALTER TABLE analytics.fact_orders ADD PRIMARY KEY (order_id);
CREATE INDEX ix_fo_purchase_date ON analytics.fact_orders (purchase_date);
CREATE INDEX ix_fo_purchase_month ON analytics.fact_orders (purchase_month);
CREATE INDEX ix_fo_customer_state ON analytics.fact_orders (customer_state);
CREATE INDEX ix_fo_customer_city ON analytics.fact_orders (customer_city);
CREATE INDEX ix_fo_status ON analytics.fact_orders (order_status);
CREATE INDEX ix_fo_customer_unique ON analytics.fact_orders (customer_unique_id);

-- ---------------------------------------------------------------------
-- fact_order_items — 1 row per order item
-- ---------------------------------------------------------------------
CREATE TABLE analytics.fact_order_items AS
SELECT
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    ct.product_category_name                   AS category_name,
    ct.product_category_name_english           AS category_english,
    ct.product_category_label                  AS category_label,
    se.seller_city,
    se.seller_state,
    ss.state_name                              AS seller_state_name,
    fo.customer_unique_id,
    fo.customer_city,
    fo.customer_state,
    fo.customer_state_name,
    fo.customer_region,
    fo.order_status,
    fo.purchase_timestamp,
    fo.purchase_date,
    fo.purchase_month,
    fo.purchase_year,
    oi.shipping_limit_date,
    oi.price,
    oi.freight_value,
    -- order-level attributes repeated on each item (for per-category / per-seller analysis)
    fo.delivery_days,
    fo.is_late,
    fo.delivery_status,
    fo.review_score
FROM raw.order_items oi
JOIN analytics.fact_orders fo    ON fo.order_id = oi.order_id
JOIN raw.products p              ON p.product_id = oi.product_id
JOIN raw.category_translation ct ON ct.product_category_name = p.product_category_name
JOIN raw.sellers se              ON se.seller_id = oi.seller_id
JOIN raw.states ss               ON ss.state_code = se.seller_state;

ALTER TABLE analytics.fact_order_items ADD PRIMARY KEY (order_id, order_item_id);
CREATE INDEX ix_foi_purchase_date ON analytics.fact_order_items (purchase_date);
CREATE INDEX ix_foi_category ON analytics.fact_order_items (category_label);
CREATE INDEX ix_foi_seller_state ON analytics.fact_order_items (seller_state);
CREATE INDEX ix_foi_customer_state ON analytics.fact_order_items (customer_state);
CREATE INDEX ix_foi_product ON analytics.fact_order_items (product_id);
CREATE INDEX ix_foi_seller ON analytics.fact_order_items (seller_id);

-- ---------------------------------------------------------------------
-- fact_payments — 1 row per payment
-- ---------------------------------------------------------------------
CREATE TABLE analytics.fact_payments AS
SELECT
    pm.order_id,
    pm.payment_sequential,
    pm.payment_type,
    CASE pm.payment_type
        WHEN 'credit_card' THEN 'Credit Card'
        WHEN 'boleto'      THEN 'Boleto'
        WHEN 'voucher'     THEN 'Voucher'
        WHEN 'debit_card'  THEN 'Debit Card'
        WHEN 'not_defined' THEN 'Not Defined'
    END                     AS payment_type_label,
    pm.payment_installments AS installments,
    pm.payment_value,
    fo.customer_unique_id,
    fo.customer_city,
    fo.customer_state,
    fo.customer_state_name,
    fo.customer_region,
    fo.order_status,
    fo.purchase_timestamp,
    fo.purchase_date,
    fo.purchase_month,
    fo.purchase_year
FROM raw.payments pm
JOIN analytics.fact_orders fo ON fo.order_id = pm.order_id;

ALTER TABLE analytics.fact_payments ADD PRIMARY KEY (order_id, payment_sequential);
CREATE INDEX ix_fp_purchase_date ON analytics.fact_payments (purchase_date);
CREATE INDEX ix_fp_type ON analytics.fact_payments (payment_type);
CREATE INDEX ix_fp_customer_state ON analytics.fact_payments (customer_state);

-- ---------------------------------------------------------------------
-- dim_customers — 1 row per real customer (customer_unique_id),
-- location taken from their most recent order
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_customers AS
WITH latest AS (
    SELECT DISTINCT ON (customer_unique_id)
           customer_unique_id, customer_zip_code_prefix, customer_city,
           customer_state, customer_state_name, customer_region
    FROM analytics.fact_orders
    ORDER BY customer_unique_id, purchase_timestamp DESC
),
agg AS (
    SELECT customer_unique_id,
           MIN(purchase_date) AS first_order_date,
           MAX(purchase_date) AS last_order_date,
           COUNT(*)::int      AS order_count
    FROM analytics.fact_orders
    GROUP BY customer_unique_id
)
SELECT l.*, a.first_order_date, a.last_order_date, a.order_count
FROM latest l
JOIN agg a USING (customer_unique_id);

ALTER TABLE analytics.dim_customers ADD PRIMARY KEY (customer_unique_id);
CREATE INDEX ix_dc_state ON analytics.dim_customers (customer_state);

-- ---------------------------------------------------------------------
-- dim_products
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_products AS
SELECT
    p.product_id,
    p.product_category_name           AS category_name,
    ct.product_category_name_english  AS category_english,
    ct.product_category_label         AS category_label,
    p.product_name_length,
    p.product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM raw.products p
JOIN raw.category_translation ct USING (product_category_name);

ALTER TABLE analytics.dim_products ADD PRIMARY KEY (product_id);
CREATE INDEX ix_dp_category ON analytics.dim_products (category_label);

-- ---------------------------------------------------------------------
-- dim_sellers
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_sellers AS
SELECT se.seller_id, se.seller_zip_code_prefix, se.seller_city, se.seller_state,
       s.state_name AS seller_state_name, s.region AS seller_region
FROM raw.sellers se
JOIN raw.states s ON s.state_code = se.seller_state;

ALTER TABLE analytics.dim_sellers ADD PRIMARY KEY (seller_id);

-- ---------------------------------------------------------------------
-- dim_geo — 1 row per zip prefix
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_geo AS
SELECT g.zip_code_prefix, g.lat, g.lng, g.city, g.state, s.state_name
FROM raw.geolocation g
JOIN raw.states s ON s.state_code = g.state;

ALTER TABLE analytics.dim_geo ADD PRIMARY KEY (zip_code_prefix);

-- ---------------------------------------------------------------------
-- dim_date — calendar 2016-01-01 .. 2018-12-31
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_date AS
WITH days AS (
    SELECT d::date AS date_day
    FROM generate_series(DATE '2016-01-01', DATE '2018-12-31', INTERVAL '1 day') AS d
),
orders_per_day AS (
    SELECT purchase_date, COUNT(*)::int AS order_count
    FROM analytics.fact_orders
    GROUP BY purchase_date
)
SELECT
    d.date_day,
    EXTRACT(YEAR FROM d.date_day)::int            AS year,
    EXTRACT(QUARTER FROM d.date_day)::int         AS quarter,
    EXTRACT(MONTH FROM d.date_day)::int           AS month,
    TRIM(TO_CHAR(d.date_day, 'Month'))            AS month_name,
    date_trunc('month', d.date_day)::date         AS month_start,
    date_trunc('quarter', d.date_day)::date       AS quarter_start,
    date_trunc('week', d.date_day)::date          AS week_start,
    EXTRACT(ISODOW FROM d.date_day)::int          AS iso_day_of_week,
    TRIM(TO_CHAR(d.date_day, 'Day'))              AS day_name,
    EXTRACT(ISODOW FROM d.date_day) IN (6, 7)     AS is_weekend,
    COALESCE(o.order_count, 0)                    AS order_count,
    COALESCE(o.order_count, 0) > 0                AS has_orders
FROM days d
LEFT JOIN orders_per_day o ON o.purchase_date = d.date_day;

ALTER TABLE analytics.dim_date ADD PRIMARY KEY (date_day);

-- ---------------------------------------------------------------------
-- meta_data_coverage — 1 row per calendar month (2016-01 .. 2018-12)
--   none    : no orders at all
--   partial : fewer than 5% of the median monthly order volume
--             (data collection starting or stopping), so totals are not comparable
--   full    : normal coverage
-- ---------------------------------------------------------------------
CREATE TABLE analytics.meta_data_coverage AS
WITH months AS (
    SELECT month_start,
           MIN(year) AS year, MIN(month) AS month, MIN(month_name) AS month_name,
           COUNT(*)::int                        AS days_in_month,
           COUNT(*) FILTER (WHERE has_orders)::int AS days_with_orders
    FROM analytics.dim_date
    GROUP BY month_start
),
orders AS (
    SELECT purchase_month,
           COUNT(*)::int                   AS order_count,
           SUM(order_revenue)::numeric(14,2) AS revenue,
           MIN(purchase_timestamp)          AS first_order_at,
           MAX(purchase_timestamp)          AS last_order_at
    FROM analytics.fact_orders
    GROUP BY purchase_month
),
joined AS (
    SELECT m.*, COALESCE(o.order_count, 0) AS order_count,
           COALESCE(o.revenue, 0)::numeric(14,2) AS revenue,
           o.first_order_at, o.last_order_at
    FROM months m
    LEFT JOIN orders o ON o.purchase_month = m.month_start
),
stats AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY order_count) AS median_orders
    FROM joined WHERE order_count > 0
)
SELECT j.month_start, j.year, j.month, j.month_name,
       j.days_in_month, j.days_with_orders,
       j.order_count, j.revenue, j.first_order_at, j.last_order_at,
       CASE WHEN j.order_count = 0 THEN 'none'
            WHEN j.order_count < 0.05 * s.median_orders THEN 'partial'
            ELSE 'full'
       END AS coverage_status
FROM joined j CROSS JOIN stats s;

ALTER TABLE analytics.meta_data_coverage ADD PRIMARY KEY (month_start);

-- ---------------------------------------------------------------------
-- Documentation + read-only access
-- ---------------------------------------------------------------------
COMMENT ON TABLE analytics.fact_orders IS 'One row per order. Revenue = sum of payments for the order; items/freight pre-aggregated per order.';
COMMENT ON TABLE analytics.fact_order_items IS 'One row per order item, with English product category and seller location.';
COMMENT ON TABLE analytics.fact_payments IS 'One row per payment, with payment type and installments.';
COMMENT ON TABLE analytics.meta_data_coverage IS 'Monthly data coverage (full/partial/none) used by the safeguards.';

GRANT USAGE ON SCHEMA analytics TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO bi_reader;

ANALYZE analytics.fact_orders;
ANALYZE analytics.fact_order_items;
ANALYZE analytics.fact_payments;
