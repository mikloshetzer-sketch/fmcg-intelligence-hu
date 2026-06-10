#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import re
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

RAW_FILE = DATA_DIR / "lidl-stores.xlsx"
OUT_FILE = DATA_DIR / "lidl-stores.json"
STATUS_FILE = DATA_DIR / "lidl-stores-status.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
SLEEP = 1.2


REGION_CITY_MAP = {
    "budapest": "Közép-Magyarország",
    "budaörs": "Közép-Magyarország",
    "budakeszi": "Közép-Magyarország",
    "budakalász": "Közép-Magyarország",
    "szigetszentmiklós": "Közép-Magyarország",
    "dunakeszi": "Közép-Magyarország",
    "érd": "Közép-Magyarország",
    "vecsés": "Közép-Magyarország",
    "gyál": "Közép-Magyarország",
    "monor": "Közép-Magyarország",
    "maglód": "Közép-Magyarország",
    "gödöllő": "Közép-Magyarország",
    "vác": "Közép-Magyarország",
    "cegléd": "Közép-Magyarország",

    "győr": "Nyugat-Dunántúl",
    "sopron": "Nyugat-Dunántúl",
    "szombathely": "Nyugat-Dunántúl",
    "zalaegerszeg": "Nyugat-Dunántúl",
    "nagykanizsa": "Nyugat-Dunántúl",
    "mosonmagyaróvár": "Nyugat-Dunántúl",
    "kőszeg": "Nyugat-Dunántúl",

    "veszprém": "Közép-Dunántúl",
    "székesfehérvár": "Közép-Dunántúl",
    "tatabánya": "Közép-Dunántúl",
    "dunaújváros": "Közép-Dunántúl",
    "esztergom": "Közép-Dunántúl",
    "ajka": "Közép-Dunántúl",
    "balatonfűzfő": "Közép-Dunántúl",

    "pécs": "Dél-Dunántúl",
    "kaposvár": "Dél-Dunántúl",
    "szekszárd": "Dél-Dunántúl",
    "siófok": "Dél-Dunántúl",
    "bonyhád": "Dél-Dunántúl",
    "barcs": "Dél-Dunántúl",
    "dombóvár": "Dél-Dunántúl",
    "fonyód": "Dél-Dunántúl",
    "marcali": "Dél-Dunántúl",
    "nagyatád": "Dél-Dunántúl",

    "miskolc": "Észak-Magyarország",
    "eger": "Észak-Magyarország",
    "salgótarján": "Észak-Magyarország",
    "kazincbarcika": "Észak-Magyarország",
    "balassagyarmat": "Észak-Magyarország",

    "debrecen": "Észak-Alföld",
    "nyíregyháza": "Észak-Alföld",
    "szolnok": "Észak-Alföld",
    "karcag": "Észak-Alföld",
    "hajdúböszörmény": "Észak-Alföld",
    "berettyóújfalu": "Észak-Alföld",
    "jászberény": "Észak-Alföld",

    "szeged": "Dél-Alföld",
    "kecskemét": "Dél-Alföld",
    "békéscsaba": "Dél-Alföld",
    "hódmezővásárhely": "Dél-Alföld",
    "baja": "Dél-Alföld",
    "gyula": "Dél-Alföld"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    if value is None:
        return ""
    value = str(value).replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value)
    value = value.strip()
    if value.lower() == "nan":
        return ""
    return value


def slugify(value):
    value = str(value).lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o",
        "ú": "u", "ü": "u", "ű": "u",
        " ": "_", "-": "_", ".": "", ",": "", "/": "_", "\\": "_",
        "(": "", ")": "", "[": "", "]": ""
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = "".join(ch for ch in value if ch.isalnum() or ch == "_")

    while "__" in value:
        value = value.replace("__", "_")

    return value.strip("_")


def region_from_city(city):
    return REGION_CITY_MAP.get(str(city or "").lower(), "n.a.")


def make_store_id(city, address, idx):
    return slugify(f"lidl_{city}_{address}_{idx}")[:100]


def parse_full_address(full_address):
    full_address = clean_text(full_address)

    postcode = ""
    city = ""
    street_address = full_address

    match = re.match(r"^(\d{4})\s+([^,]+),?\s+(.+)$", full_address)

    if match:
        postcode = match.group(1).strip()
        city = match.group(2).strip()
        street_address = match.group(3).strip()
    else:
        match_no_postcode = re.match(r"^([^,]+),\s+(.+)$", full_address)

        if match_no_postcode:
            city = match_no_postcode.group(1).strip()
            street_address = match_no_postcode.group(2).strip()

    return {
        "postcode": postcode,
        "city": city,
        "address": street_address,
        "full_address": full_address
    }


def read_raw_rows():
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Missing file: {RAW_FILE}")

    df = pd.read_excel(RAW_FILE, header=None)

    rows = []

    skip_values = {
        "lidl",
        "cím",
        "cim",
        "address",
        "full_address",
        "teljes cím",
        "teljes cim",
        "észak-közép-magyarországi üzleteink",
        "dél-magyarországi üzleteink",
        "kelet-magyarországi üzleteink",
        "nyugat-magyarországi üzleteink"
    }

    for _, row in df.iterrows():
        full_address = ""

        for value in row.tolist():
            candidate = clean_text(value)
            if candidate:
                full_address = candidate
                break

        if not full_address:
            continue

        if full_address.lower() in skip_values:
            continue

        parsed = parse_full_address(full_address)

        if not parsed["city"] or not parsed["address"]:
            continue

        rows.append(parsed)

    return rows


def geocode_city(city):
    query = f"{city}, Hungary"

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "hu"
    }

    headers = {
        "User-Agent": "fmcg-intelligence-hu-lidl-city-geocoder/1.0"
    }

    response = requests.get(
        NOMINATIM_URL,
        params=params,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()
    data = response.json()

    if not data:
        return None

    item = data[0]

    return {
        "lat": round(float(item["lat"]), 6),
        "lon": round(float(item["lon"]), 6),
        "display_name": item.get("display_name", "")
    }


def offset_point(lat, lon, idx, total):
    if total <= 1:
        return lat, lon

    angle = (2 * math.pi * idx) / total
    radius = 0.006 + 0.0015 * (idx % 4)

    offset_lat = math.sin(angle) * radius
    offset_lon = math.cos(angle) * radius

    return round(lat + offset_lat, 6), round(lon + offset_lon, 6)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()
    raw_rows = read_raw_rows()

    cities = sorted(set(row["city"] for row in raw_rows))
    city_geo = {}
    city_failed = []

    print(f"Raw Lidl rows: {len(raw_rows)}", flush=True)
    print(f"Unique cities: {len(cities)}", flush=True)

    for idx, city in enumerate(cities, start=1):
        print(f"[{idx}/{len(cities)}] City geocode: {city}", flush=True)

        try:
            geo = geocode_city(city)

            if not geo:
                city_failed.append({
                    "city": city,
                    "error": "no_result"
                })
                continue

            city_geo[city] = geo

        except Exception as exc:
            city_failed.append({
                "city": city,
                "error": str(exc)
            })

        time.sleep(SLEEP)

    stores = []
    skipped = []

    city_counter = {}

    for row in raw_rows:
        city = row["city"]

        if city not in city_geo:
            skipped.append({
                "full_address": row["full_address"],
                "city": city,
                "error": "missing_city_coordinate"
            })
            continue

        city_counter[city] = city_counter.get(city, 0) + 1

    city_seen = {}

    for idx, row in enumerate(raw_rows):
        city = row["city"]
        full_address = row["full_address"]
        street_address = row["address"]

        if city not in city_geo:
            continue

        city_seen[city] = city_seen.get(city, 0) + 1
        local_index = city_seen[city] - 1
        total_in_city = city_counter[city]

        base_lat = city_geo[city]["lat"]
        base_lon = city_geo[city]["lon"]

        lat, lon = offset_point(base_lat, base_lon, local_index, total_in_city)

        stores.append({
            "store_id": make_store_id(city, street_address, idx),
            "company": "Lidl",
            "name": f"Lidl {city}",
            "postcode": row["postcode"],
            "city": city,
            "area": city,
            "region": region_from_city(city),
            "address": full_address,
            "lat": lat,
            "lon": lon,
            "source": "lidl_static_excel_city_geocoded",
            "confidence": "city_level_estimate",
            "city_geocode_display_name": city_geo[city]["display_name"],
            "keywords": [
                f"Lidl {city}",
                full_address
            ]
        })

    payload = {
        "updated_at": updated_at,
        "version": "lidl-stores-v2-city-geocoded",
        "method_note": (
            "Statikus Lidl bolthálózati adatbázis Excelből. "
            "A koordináták városszintű Nominatim geokódolással készülnek. "
            "Ha egy városban több Lidl üzlet van, a pontok kis térképi eltolást kapnak. "
            "A darabszám pontos az Excel alapján, a koordináta városszintű becslés."
        ),
        "stores": stores
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "lidl-stores-v2-city-geocoded",
        "raw_count": len(raw_rows),
        "unique_city_count": len(cities),
        "city_geocoded_count": len(city_geo),
        "city_failed_count": len(city_failed),
        "valid_store_count": len(stores),
        "skipped_store_count": len(skipped),
        "city_failed": city_failed,
        "skipped": skipped[:100]
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Lidl stores written: {OUT_FILE}", flush=True)
    print(f"Status written: {STATUS_FILE}", flush=True)
    print(f"Valid Lidl stores: {len(stores)} / Raw rows: {len(raw_rows)}", flush=True)
    print(f"City geocoded: {len(city_geo)} / {len(cities)}", flush=True)


if __name__ == "__main__":
    main()
