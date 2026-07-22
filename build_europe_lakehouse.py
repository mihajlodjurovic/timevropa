"""
build_europe_lakehouse.py
=========================
Reads europe_merged.history_listings, normalizes via extracted_make/extracted_model,
builds Compressed Sparse Row (CSR) indexes, and exports:
  - europe_lakehouse_meta.json   (segment names, country names, array specs)
  - europe_lakehouse_data.bin    (sequential numeric arrays for zero-copy TypedArrays)

Uses array.array for memory efficiency (~160 MB instead of 10+ GB).
Single MongoDB pass + fast C-level binary writes via array.tofile().

Binary layout (all little-endian):
  HEADER:       magic:u32  count:u32  segments:u32  countries:u32  filesize:u32
  ARRAYS:       segment_ids:  u32[N]    (offset = 20)
                country_ids:  u8[N]     (offset = 20 + 4N)
                years:        u16[N]    (offset = 20 + 5N)
                prices:       i32[N]    (offset = 20 + 7N)
                predicted:    i32[N]    (offset = 20 + 11N)
                profits:      i32[N]    (offset = 20 + 15N)
                profit_pcts:  f32[N]    (offset = 20 + 19N)
                mileages:     i32[N]    (offset = 20 + 23N)
                has_images:   u8[N]     (offset = 20 + 27N)
  IMAGE URLS:   url_blob:    utf8[V]   (concatenated null-terminated URLs, variable length V)
                url_offsets: u32[N]    (byte offset into url_blob for each listing)
  SEG NAMES:    count:u32  then for each: len:u16 + utf8
  CTY NAMES:    count:u32  then for each: len:u8  + utf8
  CSR SEGMENT:  off_count:u32  offsets:u32[S+1]  mem_count:u32  members:u32[N]
  CSR COUNTRY:  off_count:u32  offsets:u32[C+1]  mem_count:u32  members:u32[N]

Target: 1M listings (configurable via TARGET variable).
Served with: python -m http.server 8080 --directory /home/djura/boraproj
"""

from pymongo import MongoClient
from urllib.parse import quote_plus
import json
import struct
import os
import array
import time
from collections import OrderedDict

USERNAME = "bogdan_lukic"
PASSWORD = "promenimee22"
HOST = "64.62.252.164"
PORT = 27017
AUTH_SOURCE = "admin"
DB_NAME = "europe_merged"
COLL_NAME = "history_listings"

OUT_DIR = "/home/djura/boraproj"
META_FILE = os.path.join(OUT_DIR, "europe_lakehouse_meta.json")
DATA_FILE = os.path.join(OUT_DIR, "europe_lakehouse_data.bin")


def connect():
    uri = f"mongodb://{USERNAME}:{quote_plus(PASSWORD)}@{HOST}:{PORT}/?authSource={AUTH_SOURCE}"
    return MongoClient(uri, serverSelectionTimeoutMS=30000)


def make_segment_key(extracted_make, extracted_model):
    make = (extracted_make or "").strip().lower()
    model = (extracted_model or "").strip().lower()
    return f"{make}|{model}"


def make_country_key(country):
    return (country or "unknown").strip().lower()


def build():
    t_total = time.time()
    client = connect()
    coll = client[DB_NAME][COLL_NAME]
    total_in_db = coll.estimated_document_count()
    print(f"Total docs in DB: {total_in_db:,}")

    # ── Single pass: collect into array.array + build vocabularies ──
    print("Pass: streaming from MongoDB into array.array...")
    t_scan = time.time()

    segment_to_id = OrderedDict()
    country_to_id = OrderedDict()

    # Typed arrays — ~45 MB for 1M listings (MUCH less than Python objects)
    seg_ids    = array.array("I")  # u32 — segment ID
    cty_ids    = array.array("B")  # u8  — country ID
    yrs        = array.array("H")  # u16 — year
    prc        = array.array("i")  # i32 — price
    pred       = array.array("i")  # i32 — predicted_price
    prof       = array.array("i")  # i32 — potential_profit
    ppct       = array.array("f")  # f32 — potential_profit_percentage
    mlg        = array.array("i")  # i32 — mileage
    has_img    = array.array("B")  # u8  — has_images bool
    img_urls_list = []              # list of str — first image URL per listing

    # CSR histograms (built during scan)
    seg_hist = {}  # seg_id -> count
    cty_hist = {}  # cty_id -> count

    required = [
        "extracted_make", "price", "year", "country",
        "predicted_price", "potential_profit", "potential_profit_percentage",
        "mileage",
    ]
    TARGET = 1_000_000  # <-- change this to adjust listing count

    cursor = coll.find(
        {f: {"$exists": True, "$ne": None} for f in required},
        no_cursor_timeout=True,
    ).batch_size(10000).limit(TARGET)

    count = 0
    log_every = 100_000

    for doc in cursor:
        # Segment
        seg = make_segment_key(doc.get("extracted_make"), doc.get("extracted_model"))
        if seg not in segment_to_id:
            segment_to_id[seg] = len(segment_to_id)
        sid = segment_to_id[seg]

        # Country
        cty = make_country_key(doc.get("country"))
        if cty not in country_to_id:
            country_to_id[cty] = len(country_to_id)
        cid = country_to_id[cty]

        # Images — bool flag + first URL
        imgs = doc.get("images")
        hi = 1 if (isinstance(imgs, list) and len(imgs) > 0) else 0
        if hi and isinstance(imgs[0], str):
            img_urls_list.append(imgs[0])
        else:
            img_urls_list.append("")

        # Append to arrays (C-level, very fast)
        seg_ids.append(sid)
        cty_ids.append(cid)
        yrs.append(max(0, min(65535, int(doc["year"]))))
        prc.append(int(doc["price"]))
        pred.append(int(doc["predicted_price"]))
        prof.append(int(doc["potential_profit"]))
        ppct.append(float(doc["potential_profit_percentage"]))
        raw_mlg = int(doc["mileage"])
        mlg.append(max(-2147483648, min(2147483647, raw_mlg)))  # clamp to i32
        has_img.append(hi)

        # Histogram
        seg_hist[sid] = seg_hist.get(sid, 0) + 1
        cty_hist[cid] = cty_hist.get(cid, 0) + 1

        count += 1
        if count % log_every == 0:
            elapsed = time.time() - t_scan
            rate = count / elapsed if elapsed > 0 else 0
            print(f"  {count:>10,} listings  |  {rate:,.0f} docs/s  "
                  f"|  {len(segment_to_id):,} segments  "
                  f"|  {len(country_to_id)} countries  "
                  f"|  mem ~{count * 27 / 2**20:.0f} MB")

    cursor.close()
    N, S, C = count, len(segment_to_id), len(country_to_id)
    scan_elapsed = time.time() - t_scan
    print(f"Scan complete: {N:,} listings in {scan_elapsed:.1f}s "
          f"({N/scan_elapsed:,.0f} docs/s)")

    # ── Build ID → name lookup ──────────────────────────────────────
    id_to_segment = [""] * S
    for seg, sid in segment_to_id.items():
        id_to_segment[sid] = seg
    id_to_country = [""] * C
    for cty, cid in country_to_id.items():
        id_to_country[cid] = cty

    # ── Build CSR indexes (in-memory, fast) ─────────────────────────
    print("Building CSR indexes...")
    t_csr = time.time()

    # Segment CSR
    seg_offsets = array.array("I", [0]) * (S + 1)
    for sid in range(S):
        seg_offsets[sid + 1] = seg_offsets[sid] + seg_hist.get(sid, 0)
    seg_members = array.array("I", [0]) * N
    seg_pos = array.array("I", seg_offsets[:-1])  # running write positions
    for i in range(N):
        sid = seg_ids[i]
        seg_members[seg_pos[sid]] = i
        seg_pos[sid] += 1

    # Country CSR
    cty_offsets = array.array("I", [0]) * (C + 1)
    for cid in range(C):
        cty_offsets[cid + 1] = cty_offsets[cid] + cty_hist.get(cid, 0)
    cty_members = array.array("I", [0]) * N
    cty_pos = array.array("I", cty_offsets[:-1])
    for i in range(N):
        cid = cty_ids[i]
        cty_members[cty_pos[cid]] = i
        cty_pos[cid] += 1

    print(f"CSR built in {time.time() - t_csr:.1f}s")

    # ── Build image URL blob + offsets ────────────────────────────
    print("Building image URL index...")
    t_img = time.time()
    img_url_bytes = bytearray()
    img_offsets = array.array("I")  # u32[N] — byte offset into URL blob
    for url in img_urls_list:
        img_offsets.append(len(img_url_bytes))
        if url:
            img_url_bytes.extend(url.encode("utf-8"))
        img_url_bytes.append(0)  # null terminator
    img_urls_mb = len(img_url_bytes) / (1024 * 1024)
    print(f"Image URLs built in {time.time() - t_img:.1f}s — {img_urls_mb:.1f} MB ({N:,} URLs)")

    # ── Write binary file ───────────────────────────────────────────
    print("Writing binary file...")
    t_write = time.time()

    with open(DATA_FILE, "wb") as f:
        # Header: magic, N, S, C, filesize (placeholder)
        f.write(struct.pack("<5I", 0x4B414B45, N, S, C, 0))
        header_end = f.tell()

        # Collect array offsets as we write
        offsets = {}
        arrays_start = f.tell()

        for name, arr in [
            ("segment_ids", seg_ids),
            ("country_ids", cty_ids),
            ("years",       yrs),
            ("prices",      prc),
            ("predicted",   pred),
            ("profits",     prof),
            ("profit_pcts", ppct),
            ("mileages",    mlg),
            ("has_images",  has_img),
        ]:
            offsets[name] = f.tell() - arrays_start
            arr.tofile(f)

        # Image URL blob: concatenated null-terminated UTF-8 URLs
        offsets["image_urls"] = f.tell() - arrays_start
        f.write(img_url_bytes)
        # Image URL offsets: u32[N] — byte offset into URL blob for each listing
        offsets["image_offsets"] = f.tell() - arrays_start
        img_offsets.tofile(f)

        # Segment names
        f.write(struct.pack("<I", S))
        for name in id_to_segment:
            b = name.encode("utf-8")
            f.write(struct.pack("<H", len(b)))
            f.write(b)

        # Country names
        f.write(struct.pack("<I", C))
        for name in id_to_country:
            b = name.encode("utf-8")
            f.write(struct.pack("<B", len(b)))
            f.write(b)

        # CSR: Segment → Listings
        f.write(struct.pack("<I", S + 1))
        seg_offsets.tofile(f)
        f.write(struct.pack("<I", N))
        seg_members.tofile(f)

        # CSR: Country → Listings
        f.write(struct.pack("<I", C + 1))
        cty_offsets.tofile(f)
        f.write(struct.pack("<I", N))
        cty_members.tofile(f)

        # Final: write filesize into header
        fsz = f.tell()
        f.seek(16)
        f.write(struct.pack("<I", fsz))

    file_mb = fsz / (1024 * 1024)
    write_elapsed = time.time() - t_write
    print(f"Written: {fsz:,} bytes ({file_mb:.1f} MB) in {write_elapsed:.1f}s")

    # ── Metadata JSON ───────────────────────────────────────────────
    print("Writing metadata JSON...")
    meta = {
        "version": 1,
        "listing_count": N,
        "segment_count": S,
        "country_count": C,
        "header_bytes": header_end,
        "arrays": {
            "segment_ids":  {"offset": offsets["segment_ids"], "type": "uint32", "bytes": 4},
            "country_ids":  {"offset": offsets["country_ids"], "type": "uint8",  "bytes": 1},
            "years":        {"offset": offsets["years"],       "type": "uint16", "bytes": 2},
            "prices":       {"offset": offsets["prices"],      "type": "int32",  "bytes": 4},
            "predicted":    {"offset": offsets["predicted"],   "type": "int32",  "bytes": 4},
            "profits":      {"offset": offsets["profits"],     "type": "int32",  "bytes": 4},
            "profit_pcts":  {"offset": offsets["profit_pcts"], "type": "float32","bytes": 4},
            "mileages":     {"offset": offsets["mileages"],    "type": "int32",  "bytes": 4},
            "has_images":   {"offset": offsets["has_images"],  "type": "uint8",  "bytes": 1},
            "image_urls":   {"offset": offsets["image_urls"],  "type": "utf8blob", "bytes": 0},
            "image_offsets":{"offset": offsets["image_offsets"],"type": "uint32", "bytes": 4},
        },
        "segments": id_to_segment,
        "countries": id_to_country,
        "segment_counts": [seg_offsets[s + 1] - seg_offsets[s] for s in range(S)],
        "country_counts": [cty_offsets[c + 1] - cty_offsets[c] for c in range(C)],
        "thin_threshold": 300,
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print("Metadata written.")

    # ── Summary ─────────────────────────────────────────────────────
    total_elapsed = time.time() - t_total
    seg_sizes = sorted(meta["segment_counts"])
    thin = sum(1 for x in seg_sizes if x < 300)

    print(f"\n{'='*60}")
    print(f"BUILD COMPLETE in {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    print(f"  Listings:  {N:>12,}")
    print(f"  Segments:  {S:>12,}  ({thin} thin, sizes {seg_sizes[0]}–{seg_sizes[-1]})")
    print(f"  Countries: {C:>12}")
    print(f"  Binary:    {file_mb:>10.1f} MB")
    print(f"\nCountries:")
    for cid in range(C):
        n = cty_offsets[cid + 1] - cty_offsets[cid]
        print(f"  {id_to_country[cid]:>20s}: {n:>10,}")

    print(f"\nFiles ready:")
    print(f"  {META_FILE}  ({os.path.getsize(META_FILE)/1024:.0f} KB)")
    print(f"  {DATA_FILE}  ({os.path.getsize(DATA_FILE)/2**20:.1f} MB)")
    print(f"\nServe:  python -m http.server 8080 --directory {OUT_DIR}")
    print(f"Open:   http://localhost:8080/seeze_europe.html")

    client.close()


if __name__ == "__main__":
    build()
