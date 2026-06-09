#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

OUT_FILE = DATA_DIR / "store-network-hu.json"
STATUS_FILE = DATA_DIR / "store-network-hu-status.json"
OVERRIDE_FILE = DATA_DIR / "store-network-overrides.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FETCH_SLEEP = 2

BRANDS = {
    "Lidl": ["Lidl", "LIDL"],
    "ALDI": ["ALDI", "Aldi"],
    "SPAR": ["SPAR", "Spar", "INTERSPAR", "Interspar"],
    "Tesco": ["Tesco", "TESCO"],
    "Auchan": ["Auchan", "AUCHAN"],
    "Penny": ["Penny", "PENNY", "Penny Market", "PENNY Market"]
}


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
    "abony": "Közép-Magyarország",
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


def make_store_id(company, name, city, source_id):
    return slugify(f"{company}_{city}_{name}_{source_id}")[:90]


def region_from_city(city):
    return REGION_CITY_MAP.get((city or "").lower(), "n.a.")


def load_existing_stores():
    if not OUT_FILE.exists():
        return []

    try:
        payload = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return payload.get("stores", [])
    except Exception:
        return []


def stores_by_company(stores, company):
    return [store for store in stores if store.get("company") == company]


def build_brand_query(brand_values):
    filters = []

    for value in brand_values:
        escaped = value.replace('"', '\\"')

        for shop_type in ["supermarket", "convenience"]:
            filters.append(f'node["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')
            filters.append(f'way["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')
            filters.append(f'relation["shop"="{shop_type}"]["brand"="{escaped}"](area.searchArea);')

    block = "\n".join(filters)

    return f"""
[out:json][timeout:180];
area["ISO3166-1"="HU"][admin_level=2]->.searchArea;
(
{block}
);
out center tags;
"""


def build_safe_name_operator_query(company):
    escaped = company.replace('"', '\\"')

    return f"""
[out:json][timeout:120];
area["ISO3166-1"="HU"][admin_level=2]->.searchArea;
(
  node["shop"="supermarket"]["name"~"^{escaped}$",i](area.searchArea);
  way["shop"="supermarket"]["name"~"^{escaped}$",i](area.searchArea);
  relation["shop"="supermarket"]["name"~"^{escaped}$",i](area.searchArea);

  node["shop"="convenience"]["name"~"^{escaped}$",i](area.searchArea);
  way["shop"="convenience"]["name"~"^{escaped}$",i](area.searchArea);
  relation["shop"="convenience"]["name"~"^{escaped}$",i](area.searchArea);

  node["shop"="supermarket"]["operator"~"^{escaped}$",i](area.searchArea);
  way["shop"="supermarket"]["operator"~"^{escaped}$",i](area.searchArea);
  relation["shop"="supermarket"]["operator"~"^{escaped}$",i](area.searchArea);
);
out center tags;
"""


def fetch_overpass(query, timeout=220):
    headers = {
        "User-Agent": "fmcg-intelligence-hu-store-network-builder/1.5"
    }

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=headers,
        timeout=timeout
    )

    response.raise_for_status()
    return response.json()


def element_coordinates(element):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]

    center = element.get("center", {})
    if "lat" in center and "lon" in center:
        return center["lat"], center["lon"]

    return None, None


def extract_city(tags):
    return (
        tags.get("addr:city")
        or tags.get("is_in:city")
        or tags.get("addr:town")
        or tags.get("addr:village")
        or tags.get("addr:suburb")
        or "n.a."
    )


def extract_address(tags):
    street = tags.get("addr:street", "")
    house = tags.get("addr:housenumber", "")
    postcode = tags.get("addr:postcode", "")
    city = extract_city(tags)

    parts = []

    if postcode and city != "n.a.":
        parts.append(f"{postcode} {city}")
    elif city != "n.a.":
        parts.append(city)

    street_line = " ".join(x for x in [street, house] if x)
    if street_line:
        parts.append(street_line)

    return ", ".join(parts) if parts else "n.a."


def normalize_company_from_tags(tags, expected_company):
    text = " ".join([
        tags.get("brand", ""),
        tags.get("name", ""),
        tags.get("operator", "")
    ]).lower()

    if "lidl" in text:
        return "Lidl"
    if "aldi" in text:
        return "ALDI"
    if "spar" in text:
        return "SPAR"
    if "tesco" in text:
        return "Tesco"
    if "auchan" in text:
        return "Auchan"
    if "penny" in text:
        return "Penny"

    return expected_company


def parse_osm_element(element, expected_company):
    tags = element.get("tags", {})
    lat, lon = element_coordinates(element)

    if lat is None or lon is None:
        return None

    company = normalize_company_from_tags(tags, expected_company)
    name = tags.get("name") or tags.get("brand") or f"{company} üzlet"
    city = extract_city(tags)
    address = extract_address(tags)

    osm_type = element.get("type", "n.a.")
    osm_id = element.get("id", "n.a.")

    return {
        "store_id": make_store_id(company, name, city, osm_id),
        "company": company,
        "name": name,
        "city": city,
        "area": city,
        "region": region_from_city(city),
        "address": address,
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "source": "openstreetmap_overpass",
        "osm_type": osm_type,
        "osm_id": osm_id,
        "brand": tags.get("brand", ""),
        "operator": tags.get("operator", ""),
        "keywords": [
            name,
            f"{company} {city}",
            address
        ]
    }


def load_overrides():
    if not OVERRIDE_FILE.exists():
        return []

    try:
        payload = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
        stores = payload.get("stores", [])

        normalized = []

        for idx, store in enumerate(stores):
            company = store.get("company", "n.a.")
            name = store.get("name", f"{company} üzlet")
            city = store.get("city", "n.a.")
            address = store.get("address", "n.a.")

            if "lat" not in store or "lon" not in store:
                continue

            normalized.append({
                "store_id": store.get("store_id") or make_store_id(company, name, city, f"override_{idx}"),
                "company": company,
                "name": name,
                "city": city,
                "area": store.get("area", city),
                "region": store.get("region") or region_from_city(city),
                "address": address,
                "lat": round(float(store.get("lat")), 6),
                "lon": round(float(store.get("lon")), 6),
                "source": store.get("source", "manual_override"),
                "confidence": store.get("confidence", "medium"),
                "keywords": store.get("keywords", [name, f"{company} {city}", address])
            })

        return normalized

    except Exception:
        return []


def deduplicate(stores):
    seen = set()
    result = []

    for store in stores:
        key = (
            store.get("company"),
            round(float(store.get("lat", 0)), 5),
            round(float(store.get("lon", 0)), 5)
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(store)

    return result


def fetch_company_stores(company, brand_values):
    stores = []
    notes = []

    try:
        data = fetch_overpass(build_brand_query(brand_values), timeout=220)

        for element in data.get("elements", []):
            store = parse_osm_element(element, company)
            if store:
                stores.append(store)

        stores = deduplicate(stores)
        notes.append(f"brand_query={len(stores)}")

    except Exception as exc:
        notes.append(f"brand_query_error={exc}")

    # Lidl esetében óvatos extra próbálkozás.
    # Nem használunk tág contains keresést, mert az akasztotta meg korábban a workflow-t.
    if company == "Lidl" and len(stores) == 0:
        try:
            data = fetch_overpass(build_safe_name_operator_query("Lidl"), timeout=150)

            for element in data.get("elements", []):
                store = parse_osm_element(element, company)
                if store:
                    stores.append(store)

            stores = deduplicate(stores)
            notes.append(f"safe_name_operator_query={len(stores)}")

        except Exception as exc:
            notes.append(f"safe_name_operator_error={exc}")

    return stores, notes


def collect_osm_stores(existing_stores):
    stores = []
    status_companies = []

    for company, brand_values in BRANDS.items():
        print(f"Fetching {company} from OSM...")

        company_stores, notes = fetch_company_stores(company, brand_values)

        if len(company_stores) == 0:
            previous = stores_by_company(existing_stores, company)

            if previous:
                company_stores = previous
                source_mode = "fallback_previous_store_network"
                status = "fallback_previous"
            else:
                source_mode = "openstreetmap_overpass"
                status = "empty"
        else:
            source_mode = "openstreetmap_overpass"
            status = "ok"

        stores.extend(company_stores)

        status_companies.append({
            "company": company,
            "source": source_mode,
            "status": status,
            "stores": len(company_stores),
            "brand_values": brand_values,
            "notes": notes
        })

        print(f"{company}: {len(company_stores)} stores ({status})")

        time.sleep(FETCH_SLEEP)

    return stores, status_companies


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()

    existing_stores = load_existing_stores()
    osm_stores, status_companies = collect_osm_stores(existing_stores)
    override_stores = load_overrides()

    all_stores = deduplicate(osm_stores + override_stores)
    all_stores.sort(key=lambda x: (x.get("company", ""), x.get("city", ""), x.get("name", "")))

    company_totals = {}
    source_totals = {}

    for store in all_stores:
        company = store.get("company", "n.a.")
        source = store.get("source", "n.a.")

        company_totals[company] = company_totals.get(company, 0) + 1
        source_totals[source] = source_totals.get(source, 0) + 1

    payload = {
        "updated_at": updated_at,
        "version": "store-network-hu-v1.5-safe-osm-with-fallback",
        "scope": "Hungarian FMCG store network from OSM + fallback + optional overrides",
        "method_note": (
            "Az országos bolthálózati adatbázis biztonságos OSM/Overpass lekérdezésekből, "
            "korábbi sikeres lekérdezések visszatartásából és opcionális override fájlból épül. "
            "Ha egy új OSM futás egy láncra 0 találatot ad, a script megtartja a korábbi store-network-hu.json "
            "adott láncra vonatkozó adatait. Ez stabilabb, mint a túl tág name/operator keresés."
        ),
        "stores": all_stores
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "store-network-hu-v1.5-safe-osm-with-fallback",
        "source": "openstreetmap_overpass_plus_fallback_plus_optional_overrides",
        "store_count": len(all_stores),
        "company_totals": company_totals,
        "source_totals": source_totals,
        "companies": status_companies,
        "filters": {
            "country": "Hungary",
            "osm_shop": ["supermarket", "convenience"],
            "searched_tag": "brand",
            "brands": BRANDS,
            "override_file": str(OVERRIDE_FILE),
            "fallback_previous_store_network": True
        }
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Store network written: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"Total stores: {len(all_stores)}")
    print(f"Company totals: {company_totals}")


if __name__ == "__main__":
    main()
