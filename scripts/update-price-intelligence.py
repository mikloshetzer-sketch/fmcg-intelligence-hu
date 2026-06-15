import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]

DATA_DIR = BASE / "docs" / "data"

PRICE_PRODUCTS = DATA_DIR / "price-products.json"
PRICE_SNAPSHOT = DATA_DIR / "price-snapshot.json"
PRICE_INTELLIGENCE = DATA_DIR / "price-intelligence.json"
PRICE_HISTORY = DATA_DIR / "price-history.json"
INSPECTION = DATA_DIR / "arfigyelo-api-inspection.json"

ARFIGYELO_BASE = "https://arfigyelo.gvh.hu/api"

COMPANIES = [
    "ALDI",
    "Auchan",
    "Lidl",
    "Penny",
    "SPAR",
    "Tesco"
]

CHAIN_NORMALIZATION = {
    "aldi": "ALDI",
    "auchan": "Auchan",
    "lidl": "Lidl",
    "penny": "Penny",
    "spar": "SPAR",
    "tesco": "Tesco"
}

BENCHMARK_BASKET = [
    {
        "id": "milk_15",
        "name": "Tej 1,5%",
        "category": "Tejtermék",
        "keywords": ["tej", "1,5"],
        "exclude": ["laktózmentes", "kakaó", "ital"]
    },
    {
        "id": "milk_28",
        "name": "Tej 2,8%",
        "category": "Tejtermék",
        "keywords": ["tej", "2,8"],
        "exclude": ["laktózmentes", "kakaó", "ital"]
    },
    {
        "id": "butter",
        "name": "Vaj",
        "category": "Tejtermék",
        "keywords": ["vaj"],
        "exclude": ["margarin", "vajkrém"]
    },
    {
        "id": "trappista",
        "name": "Trappista sajt",
        "category": "Tejtermék",
        "keywords": ["trappista"],
        "exclude": ["szeletelt"]
    },
    {
        "id": "yoghurt",
        "name": "Natúr joghurt",
        "category": "Tejtermék",
        "keywords": ["natúr", "joghurt"],
        "exclude": ["gyümölcs", "ivó"]
    },
    {
        "id": "chicken_breast",
        "name": "Csirkemellfilé",
        "category": "Húsáru",
        "keywords": ["csirkemell"],
        "exclude": ["panírozott", "sonka"]
    },
    {
        "id": "pork_leg",
        "name": "Sertéscomb",
        "category": "Húsáru",
        "keywords": ["sertéscomb"],
        "exclude": ["szeletelt", "pácolt"]
    },
    {
        "id": "minced_pork",
        "name": "Darált sertéshús",
        "category": "Húsáru",
        "keywords": ["darált", "sertés"],
        "exclude": ["marha", "mix"]
    },
    {
        "id": "turkey_breast",
        "name": "Pulykamell",
        "category": "Húsáru",
        "keywords": ["pulykamell"],
        "exclude": ["sonka", "felvágott"]
    },
    {
        "id": "potato",
        "name": "Burgonya",
        "category": "Zöldség",
        "keywords": ["burgonya"],
        "exclude": ["chips", "fagyasztott"]
    },
    {
        "id": "onion",
        "name": "Vöröshagyma",
        "category": "Zöldség",
        "keywords": ["vöröshagyma"],
        "exclude": []
    },
    {
        "id": "tomato",
        "name": "Paradicsom",
        "category": "Zöldség",
        "keywords": ["paradicsom"],
        "exclude": ["sűrített", "konzerv", "lé"]
    },
    {
        "id": "pepper",
        "name": "Paprika",
        "category": "Zöldség",
        "keywords": ["paprika"],
        "exclude": ["őrölt", "fűszer"]
    },
    {
        "id": "apple",
        "name": "Alma",
        "category": "Gyümölcs",
        "keywords": ["alma"],
        "exclude": ["lé", "püré", "ecet"]
    },
    {
        "id": "banana",
        "name": "Banán",
        "category": "Gyümölcs",
        "keywords": ["banán"],
        "exclude": ["chips"]
    },
    {
        "id": "lemon",
        "name": "Citrom",
        "category": "Gyümölcs",
        "keywords": ["citrom"],
        "exclude": ["lé", "ital"]
    },
    {
        "id": "flour",
        "name": "Finomliszt",
        "category": "Alapélelmiszer",
        "keywords": ["finomliszt"],
        "exclude": ["rétes", "teljes"]
    },
    {
        "id": "sugar",
        "name": "Kristálycukor",
        "category": "Alapélelmiszer",
        "keywords": ["kristálycukor"],
        "exclude": []
    },
    {
        "id": "rice",
        "name": "Rizs",
        "category": "Alapélelmiszer",
        "keywords": ["rizs"],
        "exclude": ["tejberizs", "készétel"]
    },
    {
        "id": "pasta",
        "name": "Száraztészta",
        "category": "Alapélelmiszer",
        "keywords": ["tészta"],
        "exclude": ["friss", "készétel"]
    },
    {
        "id": "oil",
        "name": "Étolaj",
        "category": "Alapélelmiszer",
        "keywords": ["étolaj"],
        "exclude": ["olíva"]
    },
    {
        "id": "mineral_water",
        "name": "Ásványvíz",
        "category": "Ital",
        "keywords": ["ásványvíz"],
        "exclude": ["ízesített"]
    },
    {
        "id": "cola",
        "name": "Kóla",
        "category": "Ital",
        "keywords": ["cola"],
        "exclude": ["zero", "light"]
    },
    {
        "id": "detergent",
        "name": "Mosószer",
        "category": "Háztartás",
        "keywords": ["mosószer"],
        "exclude": ["öblítő"]
    },
    {
        "id": "toilet_paper",
        "name": "Toalettpapír",
        "category": "Háztartás",
        "keywords": ["toalettpapír"],
        "exclude": []
    }
]


def utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def today():
    return datetime.utcnow().strftime("%Y-%m-%d")


def load_json(path, fallback):
    if not path.exists():
        return fallback

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def normalize_chain_name(name):
    key = str(name or "").strip().lower()
    return CHAIN_NORMALIZATION.get(key)


def normalize_text(value):
    return str(value or "").lower().strip()


def product_matches(product_name, basket_item):
    name = normalize_text(product_name)

    for keyword in basket_item["keywords"]:
        if normalize_text(keyword) not in name:
            return False

    for word in basket_item.get("exclude", []):
        if normalize_text(word) in name:
            return False

    return True


def get_normal_price(chain_store):
    prices = chain_store.get("prices", [])

    normal_prices = [
        price for price in prices
        if str(price.get("type", "")).upper() == "NORMAL"
    ]

    selected_prices = normal_prices if normal_prices else prices

    if not selected_prices:
        return None

    price = selected_prices[0]

    amount = price.get("amount")
    unit_amount = price.get("unitAmount")

    if amount is None and unit_amount is None:
        return None

    return {
        "amount": amount,
        "unit_amount": unit_amount,
        "price_type": price.get("type")
    }


def get_category_ids_from_env():
    raw = os.environ.get("ARFIGYELO_CATEGORY_IDS", "").strip()

    if not raw:
        return []

    result = []

    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            result.append(int(item))

    return result


def discover_category_ids():
    env_ids = get_category_ids_from_env()

    if env_ids:
        return env_ids, "env"

    fallback_ids = [
        2046
    ]

    return fallback_ids, "fallback"


def fetch_products_by_category(category_id, limit=100):
    products = []
    offset = 0
    total_count = None

    while True:
        query = urllib.parse.urlencode({
            "limit": limit,
            "offset": offset,
            "order": "unitAmount_asc"
        })

        url = f"{ARFIGYELO_BASE}/products-by-category/{category_id}?{query}"

        data = fetch_json(url)

        batch = data.get("products", [])
        count = data.get("count")

        if total_count is None:
            total_count = count

        products.extend(batch)

        if not batch:
            break

        offset += limit

        if total_count is not None and offset >= total_count:
            break

        time.sleep(0.4)

    return products, total_count


def collect_live_products():
    category_ids, category_source = discover_category_ids()

    all_products = []
    category_results = []

    for category_id in category_ids:
        try:
            products, count = fetch_products_by_category(category_id)

            category_results.append({
                "category_id": category_id,
                "status": "ok",
                "count": count,
                "downloaded": len(products)
            })

            all_products.extend(products)

        except Exception as error:
            category_results.append({
                "category_id": category_id,
                "status": "error",
                "error": str(error)
            })

    inspection = {
        "updated_at": utc_now(),
        "status": "ok" if all_products else "error",
        "category_source": category_source,
        "category_ids": category_ids,
        "category_results": category_results,
        "downloaded_products": len(all_products),
        "note": "Ha csak 2046 szerepel, akkor még csak a kenyér kategória aktív. További kategória ID-ket az ARFIGYELO_CATEGORY_IDS környezeti változóval lehet megadni."
    }

    save_json(INSPECTION, inspection)

    return all_products, inspection


def build_price_products(all_products):
    result_products = []

    for basket_item in BENCHMARK_BASKET:
        company_prices = {}
        selected_products = {}

        for product in all_products:
            product_name = product.get("name", "")

            if not product_matches(product_name, basket_item):
                continue

            for chain_store in product.get("pricesOfChainStores", []):
                company = normalize_chain_name(chain_store.get("name"))

                if company not in COMPANIES:
                    continue

                price_data = get_normal_price(chain_store)

                if not price_data:
                    continue

                amount = price_data.get("amount")
                unit_amount = price_data.get("unit_amount")

                comparable_price = unit_amount if unit_amount is not None else amount

                if comparable_price is None:
                    continue

                previous = company_prices.get(company)

                if previous is None or comparable_price < previous:
                    company_prices[company] = comparable_price
                    selected_products[company] = {
                        "source_product_id": product.get("id"),
                        "source_product_name": product.get("name"),
                        "amount": amount,
                        "unit_amount": unit_amount,
                        "unit": product.get("unit"),
                        "packaging": product.get("packaging"),
                        "price_type": price_data.get("price_type")
                    }

        result_products.append({
            "id": basket_item["id"],
            "product": basket_item["name"],
            "category": basket_item["category"],
            "prices": company_prices,
            "selected_products": selected_products,
            "coverage": len(company_prices)
        })

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "basket_size": len(BENCHMARK_BASKET),
        "products": result_products
    }


def calculate_company_totals(price_products):
    totals = {}

    for company in COMPANIES:
        total = 0
        covered = 0

        for product in price_products["products"]:
            price = product.get("prices", {}).get(company)

            if price is None:
                continue

            total += float(price)
            covered += 1

        totals[company] = {
            "basket_price_huf": round(total, 2),
            "covered_products": covered
        }

    return totals


def load_previous_history():
    return load_json(
        PRICE_HISTORY,
        {
            "updated_at": utc_now(),
            "history": []
        }
    )


def get_previous_history_row(history):
    rows = history.get("history", [])

    if not rows:
        return None

    rows_sorted = sorted(rows, key=lambda item: item.get("date", ""))

    if rows_sorted[-1].get("date") == today() and len(rows_sorted) > 1:
        return rows_sorted[-2]

    return rows_sorted[-1]


def calculate_weekly_change(company_totals, history):
    previous = get_previous_history_row(history)
    changes = []

    for company in COMPANIES:
        current = company_totals[company]["basket_price_huf"]

        if previous and company in previous and previous[company]:
            old = float(previous[company])
            change = ((current - old) / old) * 100 if old else 0
        else:
            change = 0

        changes.append({
            "company": company,
            "change_pct": round(change, 2)
        })

    return changes


def build_snapshot(company_totals, weekly_change):
    weekly_by_company = {
        item["company"]: item["change_pct"]
        for item in weekly_change
    }

    companies = []

    for company in COMPANIES:
        total = company_totals[company]["basket_price_huf"]
        covered = company_totals[company]["covered_products"]

        companies.append({
            "company": company,
            "basket_price_huf": total,
            "covered_products": covered,
            "weekly_change_pct": weekly_by_company.get(company, 0),
            "stability_score": None,
            "promotion_intensity": None
        })

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "companies": companies
    }


def build_price_intelligence(company_totals, weekly_change):
    valid_totals = [
        item["basket_price_huf"]
        for item in company_totals.values()
        if item["basket_price_huf"] > 0
    ]

    average = sum(valid_totals) / len(valid_totals) if valid_totals else 0

    ranking = []

    for company in COMPANIES:
        total = company_totals[company]["basket_price_huf"]
        covered = company_totals[company]["covered_products"]

        if average > 0 and total > 0:
            price_index = round((total / average) * 100)
        else:
            price_index = None

        ranking.append({
            "company": company,
            "price_index": price_index,
            "basket_price_huf": total,
            "covered_products": covered
        })

    ranking.sort(
        key=lambda item: item["price_index"] if item["price_index"] is not None else 9999
    )

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "ranking": ranking,
        "weekly_change": weekly_change
    }


def update_history(company_totals):
    history = load_previous_history()

    current_date = today()

    row = {
        "date": current_date
    }

    for company in COMPANIES:
        row[company] = company_totals[company]["basket_price_huf"]

    rows = history.get("history", [])

    rows = [
        item for item in rows
        if item.get("date") != current_date
    ]

    rows.append(row)

    rows.sort(key=lambda item: item.get("date", ""))

    history["updated_at"] = utc_now()
    history["history"] = rows

    return history


def main():
    print("GVH Árfigyelő élő adatgyűjtés indul...")

    all_products, inspection = collect_live_products()

    if not all_products:
        raise RuntimeError("Nem sikerült élő termékadatot lekérni az Árfigyelőből.")

    price_products = build_price_products(all_products)
    company_totals = calculate_company_totals(price_products)

    history_before = load_previous_history()
    weekly_change = calculate_weekly_change(company_totals, history_before)

    snapshot = build_snapshot(company_totals, weekly_change)
    intelligence = build_price_intelligence(company_totals, weekly_change)
    history = update_history(company_totals)

    save_json(PRICE_PRODUCTS, price_products)
    save_json(PRICE_SNAPSHOT, snapshot)
    save_json(PRICE_INTELLIGENCE, intelligence)
    save_json(PRICE_HISTORY, history)

    print("Árfigyelő adatgyűjtés kész.")
    print("Letöltött termékek:", inspection.get("downloaded_products"))
    print("Kosárméret:", price_products["basket_size"])
    print("Mentve:")
    print("-", PRICE_PRODUCTS)
    print("-", PRICE_SNAPSHOT)
    print("-", PRICE_INTELLIGENCE)
    print("-", PRICE_HISTORY)


if __name__ == "__main__":
    main()
