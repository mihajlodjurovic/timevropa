"""Quick MongoDB read-speed test."""
from pymongo import MongoClient
from urllib.parse import quote_plus
import time

USERNAME = "bogdan_lukic"
PASSWORD = "promenimee22"
HOST = "64.62.252.164"
PORT = 27017
AUTH = "admin"

uri = f"mongodb://{USERNAME}:{quote_plus(PASSWORD)}@{HOST}:{PORT}/?authSource={AUTH}"
client = MongoClient(uri, serverSelectionTimeoutMS=10000)
coll = client["europe_merged"]["history_listings"]

# Count
t0 = time.time()
total = coll.estimated_document_count()
print(f"Count: {total:,} in {time.time()-t0:.1f}s")

# Scan 100K
fields = {
    "extracted_make": 1, "extracted_model": 1, "price": 1,
    "year": 1, "country": 1, "predicted_price": 1,
    "potential_profit": 1, "potential_profit_percentage": 1,
    "mileage": 1, "images": 1,
}
t0 = time.time()
c = 0
for doc in coll.find(
    {"price": {"$exists": True}},
    fields,
    no_cursor_timeout=True,
).batch_size(10000).limit(100000):
    c += 1
elapsed = time.time() - t0
rate = c / elapsed if elapsed > 0 else 0
print(f"Scanned {c:,} docs in {elapsed:.1f}s = {rate:,.0f} docs/s")
est = 1_000_000 / rate if rate > 0 else 0
print(f"Estimated for 1M: {est:.0f}s = {est/60:.1f} min")

client.close()
