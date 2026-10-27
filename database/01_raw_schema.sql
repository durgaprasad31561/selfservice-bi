-- =====================================================================
-- 01_raw_schema.sql — cleaned copy of the Olist CSVs (schema "raw")
--
-- Rebuilt from scratch on every load (drop + create), so the loader is
-- idempotent and schema changes always apply. Run as bi_admin.
-- Column typos from the source (product_name_lenght, ...) are fixed here.
-- =====================================================================

SET search_path = raw;

DROP TABLE IF EXISTS
    raw.reviews, raw.payments, raw.order_items, raw.orders,
    raw.products, raw.sellers, raw.customers, raw.geolocation,
    raw.category_translation, raw.states
CASCADE;

-- ---------------------------------------------------------------------
-- Reference: the 27 Brazilian federative units (26 states + DF)
-- ---------------------------------------------------------------------
CREATE TABLE raw.states (
    state_code  CHAR(2)      PRIMARY KEY,
    state_name  VARCHAR(40)  NOT NULL UNIQUE,
    region      VARCHAR(20)  NOT NULL
);

INSERT INTO raw.states (state_code, state_name, region) VALUES
    ('AC', 'Acre',                'North'),
    ('AL', 'Alagoas',             'Northeast'),
    ('AP', 'Amapá',               'North'),
    ('AM', 'Amazonas',            'North'),
    ('BA', 'Bahia',               'Northeast'),
    ('CE', 'Ceará',               'Northeast'),
    ('DF', 'Distrito Federal',    'Center-West'),
    ('ES', 'Espírito Santo',      'Southeast'),
    ('GO', 'Goiás',               'Center-West'),
    ('MA', 'Maranhão',            'Northeast'),
    ('MT', 'Mato Grosso',         'Center-West'),
    ('MS', 'Mato Grosso do Sul',  'Center-West'),
    ('MG', 'Minas Gerais',        'Southeast'),
    ('PA', 'Pará',                'North'),
    ('PB', 'Paraíba',             'Northeast'),
    ('PR', 'Paraná',              'South'),
    ('PE', 'Pernambuco',          'Northeast'),
    ('PI', 'Piauí',               'Northeast'),
    ('RJ', 'Rio de Janeiro',      'Southeast'),
    ('RN', 'Rio Grande do Norte', 'Northeast'),
    ('RS', 'Rio Grande do Sul',   'South'),
    ('RO', 'Rondônia',            'North'),
    ('RR', 'Roraima',             'North'),
    ('SC', 'Santa Catarina',      'South'),
    ('SP', 'São Paulo',           'Southeast'),
    ('SE', 'Sergipe',             'Northeast'),
    ('TO', 'Tocantins',           'North');

-- ---------------------------------------------------------------------
-- Product categories: Portuguese key -> English name + display label
-- ---------------------------------------------------------------------
CREATE TABLE raw.category_translation (
    product_category_name          VARCHAR(80)  PRIMARY KEY,
    product_category_name_english  VARCHAR(80)  NOT NULL,
    product_category_label         VARCHAR(80)  NOT NULL
);

-- ---------------------------------------------------------------------
-- Geolocation: aggregated to ONE row per zip prefix by the loader
-- ---------------------------------------------------------------------
CREATE TABLE raw.geolocation (
    zip_code_prefix  CHAR(5)           PRIMARY KEY,
    lat              DOUBLE PRECISION  NOT NULL,
    lng              DOUBLE PRECISION  NOT NULL,
    city             VARCHAR(80)       NOT NULL,
    state            CHAR(2)           NOT NULL REFERENCES raw.states (state_code),
    source_rows      INT               NOT NULL
);

-- ---------------------------------------------------------------------
-- Customers: one row per order-customer; the real person is customer_unique_id
-- ---------------------------------------------------------------------
CREATE TABLE raw.customers (
    customer_id               CHAR(32)     PRIMARY KEY,
    customer_unique_id        CHAR(32)     NOT NULL,
    customer_zip_code_prefix  CHAR(5)      NOT NULL,
    customer_city             VARCHAR(80)  NOT NULL,
    customer_state            CHAR(2)      NOT NULL REFERENCES raw.states (state_code)
);
CREATE INDEX ix_customers_unique_id ON raw.customers (customer_unique_id);
CREATE INDEX ix_customers_state     ON raw.customers (customer_state);
CREATE INDEX ix_customers_zip       ON raw.customers (customer_zip_code_prefix);

CREATE TABLE raw.sellers (
    seller_id               CHAR(32)     PRIMARY KEY,
    seller_zip_code_prefix  CHAR(5)      NOT NULL,
    seller_city             VARCHAR(80)  NOT NULL,
    seller_state            CHAR(2)      NOT NULL REFERENCES raw.states (state_code)
);
CREATE INDEX ix_sellers_state ON raw.sellers (seller_state);

CREATE TABLE raw.products (
    product_id                  CHAR(32)     PRIMARY KEY,
    product_category_name       VARCHAR(80)  NOT NULL
        REFERENCES raw.category_translation (product_category_name),
    product_name_length         INT,
    product_description_length  INT,
    product_photos_qty          INT,
    product_weight_g            INT,
    product_length_cm           INT,
    product_height_cm           INT,
    product_width_cm            INT
);
CREATE INDEX ix_products_category ON raw.products (product_category_name);

CREATE TABLE raw.orders (
    order_id                       CHAR(32)     PRIMARY KEY,
    customer_id                    CHAR(32)     NOT NULL UNIQUE REFERENCES raw.customers (customer_id),
    order_status                   VARCHAR(20)  NOT NULL CHECK (order_status IN (
        'delivered', 'shipped', 'canceled', 'unavailable',
        'invoiced', 'processing', 'created', 'approved')),
    order_purchase_timestamp       TIMESTAMP    NOT NULL,
    order_approved_at              TIMESTAMP,
    order_delivered_carrier_date   TIMESTAMP,
    order_delivered_customer_date  TIMESTAMP,
    order_estimated_delivery_date  TIMESTAMP
);
CREATE INDEX ix_orders_purchase_ts ON raw.orders (order_purchase_timestamp);
CREATE INDEX ix_orders_status      ON raw.orders (order_status);

CREATE TABLE raw.order_items (
    order_id             CHAR(32)       NOT NULL REFERENCES raw.orders (order_id),
    order_item_id        INT            NOT NULL,
    product_id           CHAR(32)       NOT NULL REFERENCES raw.products (product_id),
    seller_id            CHAR(32)       NOT NULL REFERENCES raw.sellers (seller_id),
    shipping_limit_date  TIMESTAMP      NOT NULL,
    price                NUMERIC(12,2)  NOT NULL CHECK (price >= 0),
    freight_value        NUMERIC(12,2)  NOT NULL CHECK (freight_value >= 0),
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX ix_order_items_product ON raw.order_items (product_id);
CREATE INDEX ix_order_items_seller  ON raw.order_items (seller_id);

CREATE TABLE raw.payments (
    order_id              CHAR(32)       NOT NULL REFERENCES raw.orders (order_id),
    payment_sequential    INT            NOT NULL,
    payment_type          VARCHAR(20)    NOT NULL,
    payment_installments  INT            NOT NULL CHECK (payment_installments >= 0),
    payment_value         NUMERIC(12,2)  NOT NULL CHECK (payment_value >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);
CREATE INDEX ix_payments_type ON raw.payments (payment_type);

CREATE TABLE raw.reviews (
    review_id                CHAR(32)   PRIMARY KEY,
    order_id                 CHAR(32)   NOT NULL REFERENCES raw.orders (order_id),
    review_score             SMALLINT   NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title     TEXT,
    review_comment_message   TEXT,
    review_creation_date     TIMESTAMP  NOT NULL,
    review_answer_timestamp  TIMESTAMP
);
CREATE INDEX ix_reviews_order ON raw.reviews (order_id);
