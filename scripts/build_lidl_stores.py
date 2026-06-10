#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
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
SLEEP = 1.1


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
    "fót": "Közép-Magyarország",
    "dabas": "Közép-Magyarország",
    "dunaharaszti": "Közép-Magyarország",

    "győr": "Nyugat-Dunántúl",
    "sopron": "Nyugat-Dunántúl",
    "szombathely": "Nyugat-Dunántúl",
    "zalaegerszeg": "Nyugat-Dunántúl",
    "nagykanizsa": "Nyugat-Dunántúl",
    "mosonmagyaróvár": "Nyugat-Dunántúl",
    "celldömölk": "Nyugat-Dunántúl",

    "veszprém": "Közép-Dunántúl",
    "székesfehérvár": "Közép-Dunántúl",
    "tatabánya": "Közép-Dunántúl",
    "dunaújváros": "Közép-Dunántúl",
    "esztergom": "Közép-Dunántúl",
    "ajka": "Közép-Dunántúl",
    "balatonalmádi": "Közép-Dunántúl",
    "balatonfüred": "Közép-Dunántúl",
    "enying": "Közép-Dunántúl",

    "pécs": "Dél-Dunántúl",
    "kaposvár": "Dél-Dunántúl",
    "szekszárd": "Dél-Dunántúl",
    "siófok": "Dél-Dunántúl",
    "bonyhád": "Dél-Dunántúl",
    "balatonfenyves": "Dél-Dunántúl",
    "balatonlelle": "Dél-Dunántúl",
    "dunaföldvár": "Dél-Dunántúl",

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
    return value.strip()


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


def make_store_id(city, address):
    return slugify(f"lidl_{city}_{address}")[:90]


def parse_full_address(full_address):
    """
    Várt formák:
    1116 Budapest, Ányos utca 3.
    1158 Budapest Késmárk utca 11-13.
    Budapest, Huszti út 33.
    """
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


def geocode_lidl(row):
    postcode = row["postcode"]
    city = row["city"]
    address = row["address"]

    if postcode and city:
        query = f"Lidl, {postcode} {city}, {address}, Hungary"
    elif city:
        query = f"Lidl, {city}, {address}, Hungary"
    else:
        query = f"Lidl, {row['full_address']}, Hungary"

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "hu",
        "addressdetails": 1
    }

    headers = {
        "User-Agent": "fmcg-intelligence-hu-lidl-geocoder/1.1"
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


def read_raw_rows():
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Missing file: {RAW_FILE}")

    df = pd.read_excel(RAW_FILE, header=None)

    rows = []

    for _, row in df.iterrows():
        full_address = clean_text(row.iloc[1])

        if not full_address:
            continue

        # Fejlécsor kihagyása, ha van.
        lower = full_address.lower()
        if lower in ["cím", "cim", "address", "full_address", "teljes cím", "teljes cim"]:
            continue

        parsed = parse_full_address(full_address)

        if not parsed["address"]:
            continue

        rows.append(parsed)

    return rows


def load_existing_lidl():
    if not OUT_FILE.exists():
        return []

    try:
        payload = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return payload.get("stores", [])
    except Exception:
        return []


def existing_key(store):
    return clean_text(store.get("address", "")).lower()


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()
    raw_rows = read_raw_rows()
    existing_stores = load_existing_lidl()
    existing_by_address = {
        existing_key(store): store for store in existing_stores
    }

    stores = []
    failed = []
    reused = 0

    for idx, row in enumerate(raw_rows, start=1):
        full_address = row["full_address"]
        postcode = row["postcode"]
        city = row["city"] or "n.a."
        street_address = row["address"]

        output_address = full_address

        print(f"[{idx}/{len(raw_rows)}] Lidl geocode: {full_address}", flush=True)

        # Ha már volt egyszer sikeres geokódolás ugyanarra a címre, újrahasználjuk.
        old = existing_by_address.get(output_address.lower())

        if old and "lat" in old and "lon" in old:
            stores.append(old)
            reused += 1
            continue

        try:
            geo = geocode_lidl(row)

            if not geo:
                failed.append({
                    "full_address": full_address,
                    "error": "no_result"
                })
                continue

            stores.append({
                "store_id": make_store_id(city, street_address),
                "company": "Lidl",
                "name": f"Lidl {city}" if city != "n.a." else "Lidl",
                "postcode": postcode,
                "city": city,
                "area": city,
                "region": region_from_city(city),
                "address": output_address,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "source": "lidl_static_excel_geocoded",
                "confidence": "medium",
                "geocode_display_name": geo["display_name"],
                "keywords": [
                    f"Lidl {city}",
                    output_address
                ]
            })

        except Exception as exc:
            failed.append({
                "full_address": full_address,
                "error": str(exc)
            })

        time.sleep(SLEEP)

    payload = {
        "updated_at": updated_at,
        "version": "lidl-stores-v1.1-excel-geocoded",
        "method_note": (
            "Statikus Lidl bolthálózati adatbázis Excelből. "
            "A bemeneti Excel első oszlopa tartalmazza a teljes címet. "
            "A koordináták Nominatim geokódolással készülnek, ezért ellenőrzést igényelhetnek."
        ),
        "stores": stores
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "lidl-stores-v1.1-excel-geocoded",
        "raw_count": len(raw_rows),
        "valid_count": len(stores),
        "reused_count": reused,
        "failed_count": len(failed),
        "failed": failed[:100]
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
    print(f"Valid: {len(stores)} / Raw: {len(raw_rows)}", flush=True)
    print(f"Reused: {reused}", flush=True)
    print(f"Failed: {len(failed)}", flush=True)


if __name__ == "__main__":
    main()
