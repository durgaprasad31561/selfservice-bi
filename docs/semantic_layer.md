# Semantic layer

The semantic layer (`backend/app/semantic/model.yaml`) is the **only place where business
definitions live**. The LLM never writes business logic: it picks measures, dimensions and
filters by name, and the compiler (`backend/app/semantic/compiler.py`) turns that plan into
SQL deterministically from this file. Changing a definition here changes every answer,
dashboard widget and the data catalog page at once.

The file is validated at startup (`backend/app/semantic/loader.py`): every source, column,
filter, join and synonym is cross-checked (column references are parsed with sqlglot), and
the backend refuses to start if anything is inconsistent.

## Why measures are computed at their own grain

An order can have **several items and several payments**. Joining `order_items` to
`payments` row by row multiplies the rows: an order with 3 items and 2 payments becomes 6
rows, so summing payments triples revenue and summing prices doubles item sales.

The model avoids this in three layers:

1. **Analytics tables at one grain each** (`database/02_analytics_views.sql`):
   `fact_orders` (one row per order, payments and items pre-aggregated separately),
   `fact_order_items` (one row per item) and `fact_payments` (one row per payment).
   The loader asserts `SUM(fact_payments.payment_value) = SUM(fact_orders.order_revenue)`
   and `SUM(fact_order_items.price) = SUM(fact_orders.items_amount)`.
2. **Each measure is aggregated on its own source.** When a question mixes measures from
   different sources (e.g. Total Sales and Items Sold by state), the compiler aggregates
   each source separately in its own CTE and joins the *results* on the dimension values,
   never the fact rows.
3. **The SQL validator blocks fan-out** in custom (Mode B) SQL: joining more than two fact
   tables, or summing order-level columns after joining items to orders, is rejected.

A measure that cannot be split by a dimension is **refused, not approximated**. Example:
Total Sales is the sum of an order's payments, and an order can contain products from
several categories, so "Total Sales by Product Category" is refused and Product Sales
(item prices) is suggested instead.

## How a measure is resolved

Each measure lists one SQL aggregate per source, in order of preference. The compiler uses
the first source that supports every requested dimension and filter:

- *Order Count* by state uses `fact_orders` (`COUNT(*)`); by product category it uses
  `fact_order_items` (`COUNT(DISTINCT order_id)`: orders containing that category).
- *Average Rating* by payment type uses `fact_orders`; by product category it uses
  `fact_order_items` (average over items sold, as the definition says).

## Default business rules

Named filters are applied automatically wherever a measure declares them and are shown in
every answer's "How this was calculated" panel:

| Filter | Meaning | SQL |
|---|---|---|
| `valid_orders` | Excludes canceled and unavailable orders. | `order_status NOT IN ('canceled', 'unavailable')` |
| `delivered_orders` | Only orders that have been delivered to the customer (with a delivery date). | `delivered_date IS NOT NULL` |
| `delivered_items` | Only items whose order has been delivered to the customer. | `delivery_days IS NOT NULL` |

## Measures (19)

| Measure | Definition | Format | Computed on | Default filters | Synonyms |
|---|---|---|---|---|---|
| **Total Sales** (`total_sales`) | Revenue in BRL: the sum of all payments for orders, excluding canceled and unavailable orders. Counted once per order (payments are not multiplied by items). | currency | `fact_orders`: `SUM(order_revenue)`<br>`fact_payments`: `SUM(payment_value)` | `valid_orders` | sales, revenue, total revenue, total sales, gmv, turnover, sales value, income |
| **Order Count** (`order_count`) | Number of orders placed, in any status (including canceled). | integer | `fact_orders`: `COUNT(*)`<br>`fact_order_items`: `COUNT(DISTINCT order_id)`<br>`fact_payments`: `COUNT(DISTINCT order_id)` | - | orders, number of orders, order volume, how many orders, total orders, purchases, pedidos |
| **Average Order Value** (`average_order_value`) | Total Sales divided by the number of orders, excluding canceled and unavailable orders. Each order counted once. | currency | `fact_orders`: `SUM(order_revenue) / NULLIF(COUNT(*), 0)` | `valid_orders` | aov, avg order value, average ticket, ticket medio, average basket, average spend per order, average order size |
| **Items Sold** (`items_sold`) | Number of product units sold (order items), excluding canceled and unavailable orders. | integer | `fact_order_items`: `COUNT(*)` | `valid_orders` | items, units sold, quantity sold, products sold, number of items, units, volume sold |
| **Product Sales** (`product_sales`) | Sum of item prices in BRL (excludes freight), excluding canceled and unavailable orders. Use this to compare sales by product category or seller. | currency | `fact_order_items`: `SUM(price)`<br>`fact_orders`: `SUM(items_amount)` | `valid_orders` | product revenue, item sales, merchandise sales, category sales, sales by category, item revenue, product sales value, seller sales |
| **Shipping Cost** (`shipping_cost`) | Sum of freight charged to customers in BRL, excluding canceled and unavailable orders. | currency | `fact_order_items`: `SUM(freight_value)`<br>`fact_orders`: `SUM(freight_amount)` | `valid_orders` | freight, freight value, shipping, shipping cost, delivery cost, frete, freight cost, shipping fees |
| **Average Item Price** (`average_item_price`) | Average price of a sold item in BRL, excluding canceled and unavailable orders. | currency | `fact_order_items`: `AVG(price)` | `valid_orders` | avg price, average price, mean price, average product price, average selling price |
| **Number of Customers** (`customer_count`) | Distinct real customers (customer_unique_id) who placed at least one order. One person with several orders counts once. | integer | `fact_orders`: `COUNT(DISTINCT customer_unique_id)`<br>`fact_order_items`: `COUNT(DISTINCT customer_unique_id)`<br>`fact_payments`: `COUNT(DISTINCT customer_unique_id)` | - | customers, number of customers, unique customers, buyers, shoppers, clients, how many customers, customer base |
| **Repeat Customers** (`repeat_customers`) | Distinct customers who placed more than one order over the whole data period (Sep 2016 - Oct 2018), counted within the selected slice. | integer | `fact_orders`: `COUNT(DISTINCT CASE WHEN customer_lifetime_orders > 1 THEN customer_unique_id END)` | - | returning customers, repeat buyers, loyal customers, customers with more than one order, repeat purchasers |
| **Repeat Customer Rate** (`repeat_customer_rate`) | Repeat Customers as a percentage of Number of Customers. | percent | `fact_orders`: `100.0 * COUNT(DISTINCT CASE WHEN customer_lifetime_orders > 1 THEN customer_unique_id END) / NULLIF(COUNT(DISTINCT customer_unique_id), 0)` | - | repeat rate, retention rate, repeat purchase rate, returning customer rate, percentage of repeat customers |
| **Number of Sellers** (`seller_count`) | Distinct sellers with at least one item sold. | integer | `fact_order_items`: `COUNT(DISTINCT seller_id)` | - | sellers, number of sellers, merchants, vendors, active sellers, how many sellers, stores |
| **Average Rating** (`average_rating`) | Average customer review score (1 to 5). By order on order-level questions; by product category or seller it is the average over the items sold. | rating | `fact_orders`: `AVG(review_score)`<br>`fact_order_items`: `AVG(review_score)` | - | rating, review score, average review, avg rating, customer satisfaction, satisfaction, stars, average score |
| **Review Count** (`review_count`) | Number of customer reviews submitted. | integer | `fact_orders`: `SUM(review_count)` | - | reviews, number of reviews, how many reviews, ratings count, feedback count |
| **Average Delivery Days** (`average_delivery_days`) | Average number of days from purchase to delivery, for delivered orders only. | days | `fact_orders`: `AVG(delivery_days)`<br>`fact_order_items`: `AVG(delivery_days)` | `delivered_items`, `delivered_orders` | delivery time, average delivery time, days to deliver, shipping time, lead time, how long delivery takes, delivery speed |
| **Late Delivery Rate** (`late_delivery_rate`) | Percentage of delivered orders that arrived after the estimated delivery date. Each order counted once, also when sliced by category or seller. | percent | `fact_orders`: `100.0 * COUNT(*) FILTER (WHERE is_late) / NULLIF(COUNT(*) FILTER (WHERE is_late IS NOT NULL), 0)`<br>`fact_order_items`: `100.0 * COUNT(DISTINCT order_id) FILTER (WHERE is_late) / NULLIF(COUNT(DISTINCT order_id) FILTER (WHERE is_late IS NOT NULL), 0)` | - | late deliveries, late rate, delayed deliveries, percentage late, delay rate, on-time performance, late delivery percentage, late orders |
| **Cancellation Rate** (`cancellation_rate`) | Percentage of orders with status 'canceled' out of all orders. | percent | `fact_orders`: `100.0 * COUNT(*) FILTER (WHERE order_status = 'canceled') / NULLIF(COUNT(*), 0)`<br>`fact_order_items`: `100.0 * COUNT(DISTINCT order_id) FILTER (WHERE order_status = 'canceled') / NULLIF(COUNT(DISTINCT order_id), 0)` | - | cancel rate, canceled orders rate, cancellations, percentage canceled, order cancellation rate |
| **Average Installments** (`average_installments`) | Average number of installments per payment. | decimal | `fact_payments`: `AVG(installments)` | - | installments, avg installments, number of installments, parcelas, payment installments |
| **Payment Amount** (`payment_amount`) | Sum of payments in BRL, excluding canceled and unavailable orders. Use with Payment Type to see how much was paid with each method. | currency | `fact_payments`: `SUM(payment_value)` | `valid_orders` | payment value, amount paid, payments, payment total, payment amount by type, paid amount |
| **Number of Payments** (`payment_count`) | Number of individual payment transactions, in any order status. | integer | `fact_payments`: `COUNT(*)` | - | payment transactions, number of payments, transactions, payments count |

### Which measure can be split by which dimension

| Measure | Order Date | Customer State | Customer Region | Customer City | Seller State | Seller City | Seller | Product Category | Order Status | Payment Type | Rating | Delivery Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Total Sales | yes | yes | yes | yes | - | - | - | - | yes | yes | yes | yes |
| Order Count | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Average Order Value | yes | yes | yes | yes | - | - | - | - | yes | yes | yes | yes |
| Items Sold | yes | yes | yes | yes | yes | yes | yes | yes | yes | - | yes | yes |
| Product Sales | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Shipping Cost | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Average Item Price | yes | yes | yes | yes | yes | yes | yes | yes | yes | - | yes | yes |
| Number of Customers | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Repeat Customers | yes | yes | yes | yes | - | - | - | - | yes | yes | yes | yes |
| Repeat Customer Rate | yes | yes | yes | yes | - | - | - | - | yes | yes | yes | yes |
| Number of Sellers | yes | yes | yes | yes | yes | yes | yes | yes | yes | - | yes | yes |
| Average Rating | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Review Count | yes | yes | yes | yes | - | - | - | - | yes | yes | yes | yes |
| Average Delivery Days | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Late Delivery Rate | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Cancellation Rate | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| Average Installments | yes | yes | yes | yes | - | - | - | - | yes | yes | - | - |
| Payment Amount | yes | yes | yes | yes | - | - | - | - | yes | yes | - | - |
| Number of Payments | yes | yes | yes | yes | - | - | - | - | yes | yes | - | - |

A measure valid for two dimensions separately is not always valid for both at once (e.g. Product Sales by category uses items, by payment type uses orders); the compiler checks the exact combination and refuses it if no single source supports it.

## Dimensions (12)

| Dimension | Description | Available on | Value matching | Synonyms |
|---|---|---|---|---|
| **Order Date** (`order_date`) | Date the order was placed (purchase date). Grains: day, week, month, quarter, year (default month). | `fact_orders`, `fact_order_items`, `fact_payments` | dates | date, purchase date, order date, time, period, when, month, year |
| **Customer State** (`customer_state`) | Brazilian state of the customer (two-letter code or full name, e.g. SP / São Paulo). | `fact_orders`, `fact_order_items`, `fact_payments` | state | state, customer state, uf, estado, by state, states, province |
| **Customer Region** (`customer_region`) | Region of Brazil of the customer (North, Northeast, Center-West, Southeast, South). | `fact_orders`, `fact_order_items`, `fact_payments` | fuzzy | region, customer region, regiao, area, macro region |
| **Customer City** (`customer_city`) | City of the customer (accents are ignored, e.g. 'São Paulo' = 'sao paulo'). | `fact_orders`, `fact_order_items`, `fact_payments` | fuzzy | city, customer city, cidade, town, by city, cities |
| **Seller State** (`seller_state`) | Brazilian state where the seller is located. | `fact_order_items` | state | seller state, seller location, sellers state, merchant state, vendor state, shipped from state |
| **Seller City** (`seller_city`) | City where the seller is located. | `fact_order_items` | fuzzy | seller city, merchant city, vendor city, shipped from city |
| **Seller** (`seller`) | Individual seller, identified by an anonymised seller ID (no seller names exist). Use for seller rankings. | `fact_order_items` | exact | seller, sellers, top sellers, best sellers, vendor, vendors, merchant, merchants |
| **Product Category** (`product_category`) | English product category (e.g. 'Health & Beauty'). Only item-level measures can be split by category. | `fact_order_items` | fuzzy | category, product category, categories, product type, department, segment, by category, product line |
| **Order Status** (`order_status`) | Status of the order (Delivered, Shipped, Canceled, Unavailable, Invoiced, Processing, Created, Approved). | `fact_orders`, `fact_order_items`, `fact_payments` | fuzzy | status, order status, state of order, fulfilment status |
| **Payment Type** (`payment_type`) | Payment method (Credit Card, Boleto, Voucher, Debit Card). For order-level measures this is the method that paid the largest share of the order. | `fact_payments`, `fact_orders` | fuzzy | payment method, payment type, how customers pay, pay method, forma de pagamento, payment mode, by payment |
| **Rating** (`rating`) | Customer review score from 1 to 5 stars (rounded for orders with several reviews). | `fact_orders`, `fact_order_items` | exact | rating, stars, review score, score, star rating, rating distribution |
| **Delivery Status** (`delivery_status`) | Whether a delivered order arrived On Time or Late versus the estimated date. | `fact_orders`, `fact_order_items` | fuzzy | delivery status, on time, late, delivery performance, punctuality |

Value matching: **state** accepts the code or full name (SP, São Paulo, Sao Paulo); **fuzzy** is accent- and case-insensitive with typo tolerance ('Sao Paolo' -> 'Sao Paulo'); **exact** requires the exact value. A value that does not exist in the data is refused with suggestions.

## Sources

| Source | Table | Grain | Description |
|---|---|---|---|
| `fact_orders` | `analytics.fact_orders` | one row per order | Orders with revenue (sum of the order's payments), item and freight totals, delivery timing, average review score and customer location. |
| `fact_order_items` | `analytics.fact_order_items` | one row per order item | Individual products sold, with price, freight, English product category, seller location and the order's status, date and customer location. |
| `fact_payments` | `analytics.fact_payments` | one row per payment | Payments made for orders, with payment type and installments. |
| `dim_customers` | `analytics.dim_customers` | one row per real customer (customer_unique_id) | Customers with location from their most recent order. |
| `dim_products` | `analytics.dim_products` | one row per product | Products with English category and physical attributes. |
| `dim_sellers` | `analytics.dim_sellers` | one row per seller | Sellers and their location. |
| `dim_states` | `analytics.dim_states` | one row per Brazilian state | The 27 Brazilian federative units. |
| `dim_date` | `analytics.dim_date` | one row per calendar day (2016-01-01 to 2018-12-31) | Calendar with order counts per day. |
| `dim_geo` | `analytics.dim_geo` | one row per zip code prefix | Average latitude/longitude per zip code prefix. |

## Allowed joins

Only these joins may appear in custom SQL; the validator rejects any other.

| From | To | Type |
|---|---|---|
| `fact_order_items.order_id` | `fact_orders.order_id` | many_to_one |
| `fact_payments.order_id` | `fact_orders.order_id` | many_to_one |
| `fact_order_items.product_id` | `dim_products.product_id` | many_to_one |
| `fact_order_items.seller_id` | `dim_sellers.seller_id` | many_to_one |
| `fact_orders.customer_unique_id` | `dim_customers.customer_unique_id` | many_to_one |
| `fact_order_items.customer_unique_id` | `dim_customers.customer_unique_id` | many_to_one |
| `fact_payments.customer_unique_id` | `dim_customers.customer_unique_id` | many_to_one |
| `fact_orders.customer_state` | `dim_states.state_code` | many_to_one |
| `fact_order_items.customer_state` | `dim_states.state_code` | many_to_one |
| `fact_order_items.seller_state` | `dim_states.state_code` | many_to_one |
| `fact_payments.customer_state` | `dim_states.state_code` | many_to_one |
| `dim_customers.customer_state` | `dim_states.state_code` | many_to_one |
| `dim_sellers.seller_state` | `dim_states.state_code` | many_to_one |
| `fact_orders.purchase_date` | `dim_date.date_day` | many_to_one |
| `fact_order_items.purchase_date` | `dim_date.date_day` | many_to_one |
| `fact_payments.purchase_date` | `dim_date.date_day` | many_to_one |
| `fact_orders.customer_zip_code_prefix` | `dim_geo.zip_code_prefix` | many_to_one |
| `dim_customers.customer_zip_code_prefix` | `dim_geo.zip_code_prefix` | many_to_one |
| `dim_sellers.seller_zip_code_prefix` | `dim_geo.zip_code_prefix` | many_to_one |

## Concepts the data cannot answer

Questions mentioning these are refused before any LLM call, with the reason below.

| Concept | Example keywords | Reason | Suggestion |
|---|---|---|---|
| profit | profit, profits, profitability, net income, earnings, ebitda | The dataset contains sale prices and payments but no product or operating costs, so profit cannot be calculated. | Ask about Total Sales or Product Sales instead. |
| cost | cost, costs, cogs, cost of goods, unit cost, purchase cost | The dataset has no cost data (only freight charged to customers). | Ask about Shipping Cost (freight charged to customers) instead. |
| margin | margin, margins, markup, gross margin, profit margin | Margins need product costs, which the dataset does not contain. | Ask about Total Sales or Average Item Price instead. |
| inventory | inventory, stock, stock level, stock levels, in stock, out of stock | The dataset records sales only; it has no inventory or stock levels. | Ask about Items Sold by Product Category instead. |
| marketing | marketing, advertising, ad spend, ads, campaign, campaigns | The dataset has no marketing, advertising or campaign data. | Ask about Number of Customers or Total Sales over time instead. |
| web analytics | traffic, website visits, visitors, sessions, page views, pageviews | The dataset has no website or app traffic data. | Ask about Order Count over time instead. |
| employees | employee, employees, staff, salary, salaries, payroll | The dataset has no employee or HR data. | - |
| returns | return, returns, returned, return rate, refund, refunds | The dataset has no product return or refund records. | Ask about Cancellation Rate instead. |
| demographics | age, ages, gender, male customers, female customers, income level | The dataset has no customer demographic data (only location). | Ask about Number of Customers by Customer State instead. |
| product details | brand, brands, product name, product names, sku, model name | Products are identified only by ID and category; there are no product names or brands. | Ask about Product Category instead. |
| discounts | discount, discounts, coupon, coupons, promo code | The dataset has no discount or coupon data (vouchers appear only as a payment type). | Ask about Payment Amount by Payment Type instead. |
| taxes | tax, taxes, icms, vat, gst | The dataset has no tax data. | - |
| forecast | forecast, forecasts, predict, prediction, projection, next year | The dataset contains historical orders only (Sep 2016 - Oct 2018); it cannot forecast. | Ask about historical trends, e.g. monthly Total Sales in 2018. |
| other currency | usd, dollar, dollars, us dollars, euro, euros | All amounts are in Brazilian Real (BRL); the dataset has no exchange rates. | Ask for the amount in BRL (R$). |
| other country | india, indian, hyderabad, mumbai, delhi, bangalore | The dataset only covers orders from customers and sellers in Brazil. | Ask about a Brazilian state (e.g. São Paulo, Rio de Janeiro) or city. |

## Data coverage

Allowed values for every dimension and the monthly coverage table
(`analytics.meta_data_coverage`) are loaded from the database at startup. A month is
`none` with no orders, `partial` with fewer than 5% of the median monthly order volume, and
`full` otherwise. With the Olist data this marks Sep 2016, Dec 2016, Sep 2018 and Oct 2018
as partial and Nov 2016 as empty; questions touching them get a warning (or a refusal when
nothing matches), and charts draw those months dashed.

## Changing the model

1. Edit `backend/app/semantic/model.yaml`.
2. Restart the backend (the model is validated on startup).
3. Run `scripts\test.ps1` (every measure x dimension combination is executed on PostgreSQL).
4. Regenerate this page: `backend\.venv\Scripts\python.exe scripts\generate_semantic_docs.py`.
