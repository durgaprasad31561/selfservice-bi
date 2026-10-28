"""Load the Olist CSVs from ../data into PostgreSQL (schemas raw + analytics).

Usage (from the project root):
    backend\\.venv\\Scripts\\python.exe database\\load_data.py [--data-dir PATH]

Steps:
  1. Find each CSV by glob pattern (file names may carry prefixes).
  2. Clean it with pandas: trim text, lowercase/de-accent city names, NULL handling,
     fix category translations, deduplicate reviews, aggregate geolocation per zip.
  3. Rebuild the raw schema (01_raw_schema.sql) and bulk-load with COPY.
  4. Rebuild the analytics model (02_analytics_views.sql).
  5. Verify row counts and key business totals; exit non-zero on any mismatch.

Idempotent: every run drops and rebuilds both schemas' tables.
Connects as bi_admin using ADMIN_DATABASE_URL from the project .env.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import psycopg
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Reference data used during cleaning
# ---------------------------------------------------------------------------

#: Categories present in products but missing from the translation CSV.
MISSING_TRANSLATIONS: dict[str, str] = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_food_preparers",
}

#: Spelling fixes for English names shipped in the translation CSV.
ENGLISH_FIXES: dict[str, str] = {
    "fashio_female_clothing": "fashion_female_clothing",
    "costruction_tools_garden": "construction_tools_garden",
    "costruction_tools_tools": "construction_tools_tools",
    "home_confort": "home_comfort",
    "arts_and_craftmanship": "arts_and_craftsmanship",
}

UNKNOWN_CATEGORY = "unknown"

#: Human-readable display label for every English category name.
CATEGORY_LABELS: dict[str, str] = {
    "agro_industry_and_commerce": "Agro Industry & Commerce",
    "air_conditioning": "Air Conditioning",
    "art": "Art",
    "arts_and_craftsmanship": "Arts & Craftsmanship",
    "audio": "Audio",
    "auto": "Auto",
    "baby": "Baby",
    "bed_bath_table": "Bed, Bath & Table",
    "books_general_interest": "Books (General Interest)",
    "books_imported": "Books (Imported)",
    "books_technical": "Books (Technical)",
    "cds_dvds_musicals": "CDs, DVDs & Musicals",
    "christmas_supplies": "Christmas Supplies",
    "cine_photo": "Cinema & Photo",
    "computers": "Computers",
    "computers_accessories": "Computers & Accessories",
    "consoles_games": "Consoles & Games",
    "construction_tools_construction": "Construction Tools (Construction)",
    "construction_tools_garden": "Construction Tools (Garden)",
    "construction_tools_lights": "Construction Tools (Lights)",
    "construction_tools_safety": "Construction Tools (Safety)",
    "construction_tools_tools": "Construction Tools (Tools)",
    "cool_stuff": "Cool Stuff",
    "diapers_and_hygiene": "Diapers & Hygiene",
    "drinks": "Drinks",
    "dvds_blu_ray": "DVDs & Blu-ray",
    "electronics": "Electronics",
    "fashion_bags_accessories": "Fashion Bags & Accessories",
    "fashion_childrens_clothes": "Fashion Children's Clothes",
    "fashion_female_clothing": "Fashion Female Clothing",
    "fashion_male_clothing": "Fashion Male Clothing",
    "fashion_shoes": "Fashion Shoes",
    "fashion_sport": "Fashion Sport",
    "fashion_underwear_beach": "Fashion Underwear & Beachwear",
    "fixed_telephony": "Fixed Telephony",
    "flowers": "Flowers",
    "food": "Food",
    "food_drink": "Food & Drink",
    "furniture_bedroom": "Furniture (Bedroom)",
    "furniture_decor": "Furniture & Decor",
    "furniture_living_room": "Furniture (Living Room)",
    "furniture_mattress_and_upholstery": "Furniture (Mattress & Upholstery)",
    "garden_tools": "Garden Tools",
    "health_beauty": "Health & Beauty",
    "home_appliances": "Home Appliances",
    "home_appliances_2": "Home Appliances 2",
    "home_comfort": "Home Comfort",
    "home_comfort_2": "Home Comfort 2",
    "home_construction": "Home Construction",
    "housewares": "Housewares",
    "industry_commerce_and_business": "Industry, Commerce & Business",
    "kitchen_dining_laundry_garden_furniture": "Kitchen, Dining, Laundry & Garden Furniture",
    "la_cuisine": "La Cuisine",
    "luggage_accessories": "Luggage & Accessories",
    "market_place": "Marketplace",
    "music": "Music",
    "musical_instruments": "Musical Instruments",
    "office_furniture": "Office Furniture",
    "party_supplies": "Party Supplies",
    "pc_gamer": "PC Gamer",
    "perfumery": "Perfumery",
    "pet_shop": "Pet Shop",
    "portable_kitchen_food_preparers": "Portable Kitchen & Food Preparers",
    "security_and_services": "Security & Services",
    "signaling_and_security": "Signaling & Security",
    "small_appliances": "Small Appliances",
    "small_appliances_home_oven_and_coffee": "Small Appliances (Oven & Coffee)",
    "sports_leisure": "Sports & Leisure",
    "stationery": "Stationery",
    "tablets_printing_image": "Tablets, Printing & Image",
    "telephony": "Telephony",
    "toys": "Toys",
    "unknown": "Unknown",
    "watches_gifts": "Watches & Gifts",
}

#: Rough bounding box of Brazil; geolocation points outside it are data errors.
BRAZIL_LAT = (-33.80, 5.30)
BRAZIL_LNG = (-73.99, -34.70)

#: Source row counts from the dataset documentation.
EXPECTED_SOURCE_ROWS: dict[str, int] = {
    "orders": 99_441,
    "order_items": 112_650,
    "payments": 103_886,
    "reviews": 99_224,
    "customers": 99_441,
    "products": 32_951,
    "sellers": 3_095,
    "category_translation": 71,
    "geolocation": 1_000_163,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_env(path: Path) -> dict[str, str]:
    """Read KEY=VALUE pairs from a .env file."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def admin_dsn() -> str:
    """Return a libpq connection string for bi_admin from the environment or .env."""
    env = load_env(ROOT / ".env")
    url = os.environ.get("ADMIN_DATABASE_URL") or env.get("ADMIN_DATABASE_URL")
    if not url:
        sys.exit("ERROR: ADMIN_DATABASE_URL is not set in .env (see .env.example).")
    # SQLAlchemy URL -> libpq URL
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def find_csv(data_dir: Path, pattern: str) -> Path:
    """Find exactly one CSV in data_dir matching the glob pattern."""
    matches = sorted(data_dir.glob(pattern))
    if not matches:
        sys.exit(f"ERROR: no file matching '{pattern}' in {data_dir}")
    if len(matches) > 1:
        sys.exit(f"ERROR: several files match '{pattern}': {[m.name for m in matches]}")
    return matches[0]


def clean_text(series: pd.Series) -> pd.Series:
    """Trim whitespace and turn empty strings into NULL."""
    s = series.astype("string").str.strip()
    return s.mask(s == "")


def clean_city(series: pd.Series) -> pd.Series:
    """Lowercase, trim, remove accents and collapse inner whitespace."""
    s = clean_text(series).map(lambda v: unidecode(v) if isinstance(v, str) else v)
    return s.astype("string").str.lower().str.replace(r"\s+", " ", regex=True)


def to_ts(series: pd.Series) -> pd.Series:
    """Parse to timestamps; unparsable values become NULL."""
    return pd.to_datetime(series, errors="coerce")


def to_int(series: pd.Series) -> pd.Series:
    """Nullable integer column (written without a '.0' suffix)."""
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def zip5(series: pd.Series) -> pd.Series:
    """Zip prefixes are 5-digit strings with leading zeros."""
    return series.astype("string").str.strip().str.zfill(5)


# ---------------------------------------------------------------------------
# Cleaning, one function per table
# ---------------------------------------------------------------------------


@dataclass
class Table:
    """A cleaned dataframe ready for COPY, plus bookkeeping for the report."""

    name: str
    df: pd.DataFrame
    source_rows: int
    note: str = ""


def read(data_dir: Path, pattern: str) -> pd.DataFrame:
    """Read a CSV as strings so nothing is silently coerced."""
    return pd.read_csv(find_csv(data_dir, pattern), dtype=str, keep_default_na=False)


def clean_category_translation(data_dir: Path) -> Table:
    raw = read(data_dir, "*product_category_name_translation*.csv")
    df = pd.DataFrame(
        {
            "product_category_name": clean_text(raw["product_category_name"]),
            "product_category_name_english": clean_text(raw["product_category_name_english"]),
        }
    )
    extra = pd.DataFrame(
        {
            "product_category_name": list(MISSING_TRANSLATIONS) + [UNKNOWN_CATEGORY],
            "product_category_name_english": list(MISSING_TRANSLATIONS.values())
            + [UNKNOWN_CATEGORY],
        }
    )
    df = pd.concat([df, extra], ignore_index=True).drop_duplicates("product_category_name")
    df["product_category_name_english"] = df["product_category_name_english"].replace(ENGLISH_FIXES)
    missing_labels = set(df["product_category_name_english"]) - set(CATEGORY_LABELS)
    if missing_labels:
        sys.exit(f"ERROR: no display label for categories: {sorted(missing_labels)}")
    df["product_category_label"] = df["product_category_name_english"].map(CATEGORY_LABELS)
    return Table(
        "category_translation",
        df,
        len(raw),
        f"+{len(extra)} added ({', '.join(extra['product_category_name'])}); "
        f"{len(ENGLISH_FIXES)} English typos fixed",
    )


def clean_geolocation(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_geolocation_dataset*.csv")
    df = pd.DataFrame(
        {
            "zip_code_prefix": zip5(raw["geolocation_zip_code_prefix"]),
            "lat": pd.to_numeric(raw["geolocation_lat"], errors="coerce"),
            "lng": pd.to_numeric(raw["geolocation_lng"], errors="coerce"),
            "city": clean_city(raw["geolocation_city"]),
            "state": clean_text(raw["geolocation_state"]).str.upper(),
        }
    ).dropna()
    inside = df["lat"].between(*BRAZIL_LAT) & df["lng"].between(*BRAZIL_LNG)
    outliers = int((~inside).sum())
    df = df[inside]

    coords = df.groupby("zip_code_prefix").agg(
        lat=("lat", "mean"), lng=("lng", "mean"), source_rows=("lat", "size")
    )

    def most_common(col: str) -> pd.Series:
        counts = df.groupby(["zip_code_prefix", col]).size().reset_index(name="n")
        counts = counts.sort_values(["zip_code_prefix", "n", col], ascending=[True, False, True])
        return counts.drop_duplicates("zip_code_prefix").set_index("zip_code_prefix")[col]

    out = coords.join(most_common("city")).join(most_common("state")).reset_index()
    out = out[["zip_code_prefix", "lat", "lng", "city", "state", "source_rows"]]
    return Table(
        "geolocation",
        out,
        len(raw),
        f"aggregated to 1 row per zip; {outliers} points outside Brazil dropped",
    )


def clean_customers(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_customers_dataset*.csv")
    df = pd.DataFrame(
        {
            "customer_id": clean_text(raw["customer_id"]),
            "customer_unique_id": clean_text(raw["customer_unique_id"]),
            "customer_zip_code_prefix": zip5(raw["customer_zip_code_prefix"]),
            "customer_city": clean_city(raw["customer_city"]),
            "customer_state": clean_text(raw["customer_state"]).str.upper(),
        }
    )
    return Table("customers", df, len(raw))


def clean_sellers(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_sellers_dataset*.csv")
    df = pd.DataFrame(
        {
            "seller_id": clean_text(raw["seller_id"]),
            "seller_zip_code_prefix": zip5(raw["seller_zip_code_prefix"]),
            "seller_city": clean_city(raw["seller_city"]),
            "seller_state": clean_text(raw["seller_state"]).str.upper(),
        }
    )
    return Table("sellers", df, len(raw))


def clean_products(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_products_dataset*.csv")
    category = clean_text(raw["product_category_name"])
    unknown = int(category.isna().sum())
    df = pd.DataFrame(
        {
            "product_id": clean_text(raw["product_id"]),
            "product_category_name": category.fillna(UNKNOWN_CATEGORY),
            # source typo "lenght" fixed here
            "product_name_length": to_int(raw["product_name_lenght"]),
            "product_description_length": to_int(raw["product_description_lenght"]),
            "product_photos_qty": to_int(raw["product_photos_qty"]),
            "product_weight_g": to_int(raw["product_weight_g"]),
            "product_length_cm": to_int(raw["product_length_cm"]),
            "product_height_cm": to_int(raw["product_height_cm"]),
            "product_width_cm": to_int(raw["product_width_cm"]),
        }
    )
    return Table("products", df, len(raw), f"{unknown} without category -> 'unknown'")


def clean_orders(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_orders_dataset*.csv")
    df = pd.DataFrame(
        {
            "order_id": clean_text(raw["order_id"]),
            "customer_id": clean_text(raw["customer_id"]),
            "order_status": clean_text(raw["order_status"]).str.lower(),
            "order_purchase_timestamp": to_ts(raw["order_purchase_timestamp"]),
            "order_approved_at": to_ts(raw["order_approved_at"]),
            "order_delivered_carrier_date": to_ts(raw["order_delivered_carrier_date"]),
            "order_delivered_customer_date": to_ts(raw["order_delivered_customer_date"]),
            "order_estimated_delivery_date": to_ts(raw["order_estimated_delivery_date"]),
        }
    )
    return Table("orders", df, len(raw))


def clean_order_items(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_order_items_dataset*.csv")
    df = pd.DataFrame(
        {
            "order_id": clean_text(raw["order_id"]),
            "order_item_id": to_int(raw["order_item_id"]),
            "product_id": clean_text(raw["product_id"]),
            "seller_id": clean_text(raw["seller_id"]),
            "shipping_limit_date": to_ts(raw["shipping_limit_date"]),
            "price": pd.to_numeric(raw["price"]).round(2),
            "freight_value": pd.to_numeric(raw["freight_value"]).round(2),
        }
    )
    return Table("order_items", df, len(raw))


def clean_payments(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_order_payments_dataset*.csv")
    df = pd.DataFrame(
        {
            "order_id": clean_text(raw["order_id"]),
            "payment_sequential": to_int(raw["payment_sequential"]),
            "payment_type": clean_text(raw["payment_type"]).str.lower(),
            "payment_installments": to_int(raw["payment_installments"]),
            "payment_value": pd.to_numeric(raw["payment_value"]).round(2),
        }
    )
    return Table("payments", df, len(raw))


def clean_reviews(data_dir: Path) -> Table:
    raw = read(data_dir, "*olist_order_reviews_dataset*.csv")
    df = pd.DataFrame(
        {
            "review_id": clean_text(raw["review_id"]),
            "order_id": clean_text(raw["order_id"]),
            "review_score": to_int(raw["review_score"]),
            "review_comment_title": clean_text(raw["review_comment_title"]),
            "review_comment_message": clean_text(raw["review_comment_message"]),
            "review_creation_date": to_ts(raw["review_creation_date"]),
            "review_answer_timestamp": to_ts(raw["review_answer_timestamp"]),
        }
    )
    # Keep the most recently answered copy of each duplicated review_id.
    df = df.sort_values(["review_id", "review_answer_timestamp"], ascending=[True, False])
    deduped = df.drop_duplicates("review_id", keep="first")
    removed = len(df) - len(deduped)
    return Table("reviews", deduped, len(raw), f"{removed} duplicate review_id rows removed")


#: Load order respects foreign keys.
CLEANERS: list[Callable[[Path], Table]] = [
    clean_category_translation,
    clean_geolocation,
    clean_customers,
    clean_sellers,
    clean_products,
    clean_orders,
    clean_order_items,
    clean_payments,
    clean_reviews,
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def copy_dataframe(cur: psycopg.Cursor, table: str, df: pd.DataFrame) -> None:
    """Bulk-load a dataframe with COPY ... FROM STDIN (CSV, empty = NULL)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="", date_format="%Y-%m-%d %H:%M:%S")
    columns = ", ".join(df.columns)
    with cur.copy(f"COPY raw.{table} ({columns}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
        cp.write(buf.getvalue())


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Execute a multi-statement SQL script."""
    conn.execute(path.read_text(encoding="utf-8"))


def scalar(conn: psycopg.Connection, query: str) -> object:
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def verify(conn: psycopg.Connection, tables: list[Table]) -> list[str]:
    """Print row counts and business totals; return a list of failures."""
    failures: list[str] = []
    print("\nRow counts (raw schema)")
    print(f"  {'table':<22}{'source':>12}{'expected':>12}{'loaded':>12}  notes")
    for t in tables:
        loaded = scalar(conn, f"SELECT COUNT(*) FROM raw.{t.name}")
        expected = EXPECTED_SOURCE_ROWS[t.name]
        flag = "" if t.source_rows == expected else "  <-- SOURCE MISMATCH"
        if t.source_rows != expected:
            failures.append(f"{t.name}: source has {t.source_rows}, expected {expected}")
        if loaded != len(t.df):
            failures.append(f"{t.name}: cleaned {len(t.df)} rows but loaded {loaded}")
        print(f"  {t.name:<22}{t.source_rows:>12,}{expected:>12,}{loaded:>12,}  {t.note}{flag}")

    print("\nAnalytics model")
    checks = [
        ("fact_orders rows", "SELECT COUNT(*) FROM analytics.fact_orders", 99_441, 0),
        ("fact_order_items rows", "SELECT COUNT(*) FROM analytics.fact_order_items", 112_650, 0),
        ("fact_payments rows", "SELECT COUNT(*) FROM analytics.fact_payments", 103_886, 0),
        (
            "distinct customers",
            "SELECT COUNT(DISTINCT customer_unique_id) FROM analytics.fact_orders",
            96_096,
            0,
        ),
        ("dim_customers rows", "SELECT COUNT(*) FROM analytics.dim_customers", 96_096, 0),
        (
            "total payment revenue (BRL)",
            "SELECT SUM(order_revenue) FROM analytics.fact_orders",
            16_008_872.12,
            1.0,
        ),
        (
            "revenue grain check (payments = orders)",
            "SELECT (SELECT SUM(payment_value) FROM analytics.fact_payments)"
            " - (SELECT SUM(order_revenue) FROM analytics.fact_orders)",
            0,
            0.01,
        ),
        (
            "items grain check (items = orders)",
            "SELECT (SELECT SUM(price) FROM analytics.fact_order_items)"
            " - (SELECT SUM(items_amount) FROM analytics.fact_orders)",
            0,
            0.01,
        ),
        (
            "products without category",
            "SELECT COUNT(*) FROM analytics.dim_products WHERE category_name = 'unknown'",
            610,
            0,
        ),
        ("states", "SELECT COUNT(*) FROM analytics.dim_states", 27, 0),
    ]
    for label, query, expected, tolerance in checks:
        value = scalar(conn, query)
        ok = abs(float(value) - float(expected)) <= tolerance
        if not ok:
            failures.append(f"{label}: got {value}, expected {expected}")
        shown = f"{float(value):,.2f}" if isinstance(expected, float) else f"{int(value):,}"
        status = "OK" if ok else f"FAIL (expected {expected})"
        print(f"  {label:<42}{shown:>18}  {status}")

    rows = conn.execute(
        "SELECT to_char(month_start, 'YYYY-MM'), order_count, coverage_status "
        "FROM analytics.meta_data_coverage WHERE coverage_status <> 'full' "
        "AND month_start BETWEEN '2016-09-01' AND '2018-10-01' ORDER BY month_start"
    ).fetchall()
    print("\nNon-full months inside the data range (meta_data_coverage)")
    for month, count, status in rows:
        print(f"  {month}: {count:>5} orders  -> {status}")
    first, last = conn.execute(
        "SELECT MIN(purchase_timestamp), MAX(purchase_timestamp) FROM analytics.fact_orders"
    ).fetchone()
    print(f"  order date range: {first} .. {last}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--database-url",
        help="target database (overrides ADMIN_DATABASE_URL), e.g. a cloud Postgres URL",
    )
    parser.add_argument(
        "--drop-raw",
        action="store_true",
        help="after a successful load, drop the raw tables (only analytics is needed at run "
        "time; saves ~145 MB on free cloud plans)",
    )
    args = parser.parse_args()
    data_dir: Path = args.data_dir.resolve()
    dsn = (
        args.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if args.database_url
        else admin_dsn()
    )

    started = time.perf_counter()
    print(f"Reading and cleaning CSVs from {data_dir}")
    tables: list[Table] = []
    for cleaner in CLEANERS:
        t0 = time.perf_counter()
        table = cleaner(data_dir)
        tables.append(table)
        print(f"  {table.name:<22}{len(table.df):>10,} rows  ({time.perf_counter() - t0:.1f}s)")

    print("\nConnecting to the database and rebuilding the raw schema")
    with psycopg.connect(dsn) as conn:
        run_sql_file(conn, DB_DIR / "01_raw_schema.sql")
        with conn.cursor() as cur:
            for table in tables:
                t0 = time.perf_counter()
                copy_dataframe(cur, table.name, table.df)
                print(f"  COPY raw.{table.name:<22} {time.perf_counter() - t0:.1f}s")
        conn.execute("ANALYZE")
        print("Building the analytics model")
        t0 = time.perf_counter()
        run_sql_file(conn, DB_DIR / "02_analytics_views.sql")
        print(f"  analytics rebuilt in {time.perf_counter() - t0:.1f}s")
        conn.commit()

        failures = verify(conn, tables)

        if args.drop_raw and not failures:
            names = ", ".join(f"raw.{t.name}" for t in tables) + ", raw.states"
            conn.execute(f"DROP TABLE IF EXISTS {names} CASCADE")
            conn.commit()
            size = conn.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ).fetchone()[0]
            print(f"\nRaw tables dropped (analytics kept). Database size now: {size}")

    print(f"\nFinished in {time.perf_counter() - started:.1f}s")
    if failures:
        print("\nVERIFICATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All verification checks passed.")


if __name__ == "__main__":
    main()
