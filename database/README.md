# Database

PostgreSQL (16+, installed locally; no Docker). Database `bi_db`, three schemas:

| Schema | Owner | Purpose | Who reads it |
|---|---|---|---|
| `raw` | `bi_admin` | Cleaned copy of the 9 Olist CSVs, with PKs, FKs and indexes | loader only |
| `analytics` | `bi_admin` | Business model at the correct grain (facts + dimensions) | `bi_reader` (all user queries) |
| `app` | `bi_admin` | Users, dashboards, widgets, query history (created by the backend) | backend |

`bi_reader` has `SELECT` on `analytics` only, `default_transaction_read_only = on` and
`search_path = analytics`. It cannot see `raw` or `app`.

## Files

| File | What it does |
|---|---|
| `01_raw_schema.sql` | Drops and recreates the `raw` tables, seeds the 27 Brazilian states |
| `02_analytics_views.sql` | Drops and rebuilds the `analytics` tables from `raw` |
| `load_data.py` | Finds CSVs by pattern, cleans them, `COPY`-loads `raw`, builds `analytics`, verifies |

## Load

```powershell
scripts\setup.ps1        # once: database, schemas, roles
scripts\load_data.ps1    # any time: full, idempotent rebuild (~1.5 min)
```

The loader exits non-zero if any verification check fails.

## Cleaning rules

| Issue | Handling |
|---|---|
| File names may have prefixes | Found by glob, e.g. `*olist_orders_dataset*.csv` |
| City names | trimmed, lowercased, accents removed (`São Paulo` → `sao paulo`) |
| Zip prefixes | kept as 5-character strings (leading zeros preserved) |
| Column typos | `product_name_lenght` → `product_name_length`, same for description |
| 610 products without category | category `unknown` |
| 2 categories missing from translation file | added: `pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos` → `portable_kitchen_food_preparers` |
| Typos in English category names | fixed (`fashio_female_clothing`, `costruction_tools_*`, `home_confort`, `arts_and_craftmanship`) |
| Portuguese/technical category names | every category gets a display label (`health_beauty` → "Health & Beauty") |
| 814 duplicate `review_id`s | one row kept (latest answer) |
| Geolocation: ~1M rows, many per zip | 42 points outside Brazil dropped; then 1 row per zip (mean lat/lng, most common city/state) |

## Analytics model

| Table | Grain | Notes |
|---|---|---|
| `fact_orders` | 1 row per order | `order_revenue` = sum of that order's payments; `items_amount`, `freight_amount`, `item_count` = sums of that order's items; `delivery_days`, `is_late`, `delivery_status`, avg `review_score`, `primary_payment_type` (largest payment), `installments` |
| `fact_order_items` | 1 row per item | English category + label, seller city/state, customer location, order status and purchase date |
| `fact_payments` | 1 row per payment | payment type code + label, installments, value, customer location, order status and date |
| `dim_customers` | 1 row per `customer_unique_id` | location from latest order, first/last order date, order count |
| `dim_products`, `dim_sellers`, `dim_states`, `dim_geo` | 1 row per key | descriptive attributes |
| `dim_date` | 1 row per day, 2016-01-01 .. 2018-12-31 | grains + `has_orders` |
| `meta_data_coverage` | 1 row per month, 2016-01 .. 2018-12 | `none` (0 orders), `partial` (< 5% of median monthly orders), `full` |

**Why per-grain tables?** An order can have several items *and* several payments. Joining
`order_items` to `payments` row-by-row multiplies rows and inflates both sums. Payments and
items are therefore aggregated separately per order before being combined in `fact_orders`.
The loader asserts that `SUM(fact_payments.payment_value) = SUM(fact_orders.order_revenue)`
and `SUM(fact_order_items.price) = SUM(fact_orders.items_amount)`.

Business rules such as "revenue excludes canceled and unavailable orders" live in the semantic
layer (`backend/app/semantic/model.yaml`), not in these tables.

## Verified figures

| Check | Value |
|---|---|
| Orders | 99,441 |
| Order items | 112,650 |
| Payments | 103,886 |
| Distinct customers (`customer_unique_id`) | 96,096 |
| Total payment revenue (all statuses) | R$ 16,008,872.12 |
| Order date range | 2016-09-04 .. 2018-10-17 |
| Partial months | 2016-09 (4), 2016-12 (1), 2018-09 (16), 2018-10 (4) |
| Months with no orders inside range | 2016-11 |
