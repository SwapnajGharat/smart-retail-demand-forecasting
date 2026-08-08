import sys
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, UpdateOne


URI = "mongodb://localhost:27017/"
DB_NAME = "smart_retail_db"
CSV_PATH = Path(__file__).resolve().parent / "sales_data.csv"
BATCH_SIZE = 2000


def load_dataframe(csv_path: Path) -> pd.DataFrame:
    print(f"Loading CSV data from {csv_path}...")
    df = pd.read_csv(csv_path)
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d", errors="coerce")
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def upsert_batch(collection, operations):
    if not operations:
        return
    collection.bulk_write(operations, ordered=False)


def ingest_data():
    print(f"Connecting to MongoDB at {URI}...")
    client = MongoClient(URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        raise RuntimeError(f"Unable to reach MongoDB at {URI}: {exc}") from exc

    db = client[DB_NAME]
    print(f"Connected successfully to database '{DB_NAME}'.")

    df = load_dataframe(CSV_PATH)
    total_rows = len(df)
    print(f"Preparing to ingest {total_rows} rows into MongoDB collections...")

    stores_collection = db["stores"]
    products_collection = db["products"]
    sales_collection = db["sales_transactions"]
    external_collection = db["external_factors"]
    inventory_collection = db["inventory_snapshots"]

    store_ops = []
    product_ops = []
    sales_ops = []
    external_ops = []
    inventory_ops = []

    seen_stores = set()
    seen_products = set()
    seen_external = set()
    seen_inventory = set()

    for index, row in df.iterrows():
        store_id = str(row["Store ID"])
        product_id = str(row["Product ID"])
        date_value = row["Date"]

        if store_id not in seen_stores:
            seen_stores.add(store_id)
            store_ops.append(
                UpdateOne(
                    {"_id": store_id},
                    {"$set": {"_id": store_id, "region": row["Region"]}},
                    upsert=True,
                )
            )

        if product_id not in seen_products:
            seen_products.add(product_id)
            product_ops.append(
                UpdateOne(
                    {"_id": product_id},
                    {
                        "$set": {
                            "_id": product_id,
                            "category": row["Category"],
                            "price": float(row["Price"]),
                        }
                    },
                    upsert=True,
                )
            )

        sales_id = f"TXN_{store_id}_{product_id}_{date_value}"
        sales_ops.append(
            UpdateOne(
                {"_id": sales_id},
                {
                    "$set": {
                        "_id": sales_id,
                        "date": date_value,
                        "store_id": store_id,
                        "product_id": product_id,
                        "units_sold": int(row["Units Sold"]),
                        "units_ordered": int(row["Units Ordered"]),
                        "price": float(row["Price"]),
                        "discount": float(row["Discount"]),
                        "demand": int(row["Demand"]),
                    }
                },
                upsert=True,
            )
        )

        external_id = f"EXT_{store_id}_{date_value}"
        if external_id not in seen_external:
            seen_external.add(external_id)
            external_ops.append(
                UpdateOne(
                    {"_id": external_id},
                    {
                        "$set": {
                            "_id": external_id,
                            "date": date_value,
                            "store_id": store_id,
                            "weather_condition": row["Weather Condition"],
                            "promotion": row["Promotion"],
                            "competitor_pricing": float(row["Competitor Pricing"]),
                            "seasonality": row["Seasonality"],
                            "epidemic": row["Epidemic"],
                        }
                    },
                    upsert=True,
                )
            )

        inventory_id = f"INV_{store_id}_{product_id}_{date_value}"
        if inventory_id not in seen_inventory:
            seen_inventory.add(inventory_id)
            inventory_ops.append(
                UpdateOne(
                    {"_id": inventory_id},
                    {
                        "$set": {
                            "_id": inventory_id,
                            "date": date_value,
                            "store_id": store_id,
                            "product_id": product_id,
                            "inventory_level": int(row["Inventory Level"]),
                            "was_stocked_out": int(row["Inventory Level"]) == 0,
                        }
                    },
                    upsert=True,
                )
            )

        if (index + 1) % BATCH_SIZE == 0 or (index + 1) == total_rows:
            print(f"Processing rows {max(0, index + 1 - BATCH_SIZE + 1)}-{index + 1} of {total_rows}...")
            upsert_batch(stores_collection, store_ops)
            store_ops = []
            upsert_batch(products_collection, product_ops)
            product_ops = []
            upsert_batch(sales_collection, sales_ops)
            sales_ops = []
            upsert_batch(external_collection, external_ops)
            external_ops = []
            upsert_batch(inventory_collection, inventory_ops)
            inventory_ops = []

    print("Creating performance indexes...")
    sales_collection.create_index([("date", 1), ("store_id", 1), ("product_id", 1)])
    external_collection.create_index([("date", 1), ("store_id", 1)])
    inventory_collection.create_index([("date", 1), ("store_id", 1), ("product_id", 1)])

    print("Ingestion completed successfully.")
    client.close()


if __name__ == "__main__":
    try:
        ingest_data()
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        sys.exit(1)
