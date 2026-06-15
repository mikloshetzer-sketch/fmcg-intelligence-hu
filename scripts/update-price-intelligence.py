import json
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

ARFIGYELO_BASE = "https://arfigyelo.gvh.hu/api"

COMPANIES = ["ALDI", "Auchan", "Lidl", "Penny", "SPAR", "Tesco"]

CHAIN_NORMALIZATION = {
    "aldi": "ALDI",
    "auchan": "Auchan",
    "lidl": "Lidl",
    "penny": "Penny",
    "spar": "SPAR",
    "tesco": "Tesco"
}

BENCHMARK_CATEGORIES = [
    {"id": 2, "name": "ESL tej 1,5%", "category": "Tejtermék"},
    {"id": 1, "name": "ESL tej 2,8%", "category": "Tejtermék"},
    {"id": 7, "name": "Natúr joghurt", "category": "Tejtermék"},
    {"id": 10, "name": "Trappista sajt", "category": "Tejtermék"},
    {"id": 12, "name": "Vaj", "category": "Tejtermék"},
    {"id": 14, "name": "Tojás", "category": "Frissáru"},
    {"id": 15, "name": "Sertéscomb", "category": "Húsáru"},
    {"id": 85, "name": "Darált sertéshús", "category": "Húsáru"},
    {"id": 18, "name": "Csirkemellfilé", "category": "Húsáru"},
    {"id": 21, "name": "Pulykamellfilé", "category": "Húsáru"},
    {"id": 28, "name": "Alma", "category": "Gyümölcs"},
    {"id": 31, "name": "Banán", "category": "Gyümölcs"},
    {"id": 32, "name": "Citrom", "category": "Gyümölcs"},
    {"id": 34, "name": "Paradicsom", "category": "Zöldség"},
    {"id": 35, "name": "Zöldpaprika", "category": "Zöldség"},
    {"id": 40, "name": "Vöröshagyma", "category": "Zöldség"},
    {"id": 41, "name": "Étkezési burgonya", "category": "Zöldség"},
    {"id": 50, "name": "Száraztészta", "category": "Alapélelmiszer"},
    {"id": 51, "name": "Étolaj", "category": "Alapélelmiszer"},
    {"id": 52, "name": "Finomliszt", "category": "Alapélelmiszer"},
    {"id": 54, "name": "Kristálycukor", "category": "Alapélelmiszer"},
    {"id": 67, "name": "Ásványvíz", "category": "Ital"},
    {"id": 95, "name": "Rizs", "category": "Alapélelmiszer"},
    {"id": 126, "name": "Toalettpapír", "category": "Háztartás"},
    {"id": 131, "name": "Folyékony mosószer", "category": "Háztartás"}
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
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_chain_name(name):
    return CHAIN_NORMALIZATION.get(str(name or "").strip().lower())


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

        time.sleep(0.2)

    return products


def get_normal_price(chain_store):
    prices = chain_store.get("prices", [])

    normal_prices = [
        price for price in prices
        if str(price.get("type", "")).upper() == "NORMAL"
    ]

    selected = normal_prices if normal_prices else prices

    if not selected:
        return None

    price = selected[0]

    amount = price.get("amount")
    unit_amount = price.get("unitAmount")

    if amount is None and unit_amount is None:
        return None

    return {
        "amount": amount,
        "unit_amount": unit_amount,
        "price_type": price.get("type")
    }


def build_price_products():
    result_products = []

    for item in BENCHMARK_CATEGORIES:
        print(f"Lekérés: {item['id']} - {item['name']}")

        products = fetch_products_by_category(item["id"])

        company_prices = {}
        selected_products = {}

        for product in products:
            for chain_store in product.get("pricesOfChainStores", []):
                company = normalize_chain_name(chain_store.get("name"))

                if company not in COMPANIES:
                    continue

                price_data = get_normal_price(chain_store)

                if not price_data:
                    continue

                comparable_price = price_data["unit_amount"] if price_data["unit_amount"] is not None else price_data["amount"]

                if comparable_price is None:
                    continue

                previous = company_prices.get(company)

                if previous is None or comparable_price < previous:
                    company_prices[company] = comparable_price
                    selected_products[company] = {
                        "source_product_id": product.get("id"),
                        "source_product_name": product.get("name"),
                        "amount": price_data["amount"],
                        "unit_amount": price_data["unit_amount"],
                        "unit": product.get("unit"),
                        "packaging": product.get("packaging"),
                        "price_type": price_data["price_type"]
                    }

        result_products.append({
            "id": str(item["id"]),
            "product": item["name"],
            "category": item["category"],
            "prices": company_prices,
            "selected_products": selected_products,
            "coverage": len(company_prices)
        })

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "basket_size": len(BENCHMARK_CATEGORIES),
        "products": result_products
    }


def validate_coverage(price_products):
    covered_items = sum(
        1 for product in price_products["products"]
        if product.get("coverage", 0) > 0
    )

    total_hits = sum(
        product.get("coverage", 0)
        for product in price_products["products"]
    )

    if covered_items == 0 or total_hits == 0:
        raise RuntimeError("Nincs lefedett termék. Nem írunk adatfájlokat.")

    print(f"Lefedett kosártermékek: {covered_items}/{price_products['basket_size']}")
    print(f"Összes láncár-találat: {total_hits}")


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


def load_history():
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

    rows = sorted(rows, key=lambda item: item.get("date", ""))

    if rows[-1].get("date") == today() and len(rows) > 1:
        return rows[-2]

    return rows[-1]


def calculate_weekly_change(company_totals, history):
    previous = get_previous_history_row(history)
    changes = []

    for company in COMPANIES:
        current = company_totals[company]["basket_price_huf"]

        if current <= 0:
            change = None
        elif previous and company in previous and previous[company] and float(previous[company]) > 0:
            old = float(previous[company])
            change = round(((current - old) / old) * 100, 2)
        else:
            change = 0

        changes.append({
            "company": company,
            "change_pct": change
        })

    return changes


def build_snapshot(company_totals, weekly_change):
    weekly = {
        item["company"]: item["change_pct"]
        for item in weekly_change
    }

    companies = []

    for company in COMPANIES:
        companies.append({
            "company": company,
            "basket_price_huf": company_totals[company]["basket_price_huf"],
            "covered_products": company_totals[company]["covered_products"],
            "weekly_change_pct": weekly.get(company),
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

    average = sum(valid_totals) / len(valid_totals)

    ranking = []

    for company in COMPANIES:
        total = company_totals[company]["basket_price_huf"]
        covered = company_totals[company]["covered_products"]

        price_index = round((total / average) * 100) if total > 0 else None

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
    history = load_history()

    row = {
        "date": today()
    }

    for company in COMPANIES:
        row[company] = company_totals[company]["basket_price_huf"]

    rows = [
        item for item in history.get("history", [])
        if item.get("date") != today()
    ]

    rows.append(row)
    rows.sort(key=lambda item: item.get("date", ""))

    return {
        "updated_at": utc_now(),
        "history": rows
    }


def main():
    print("GVH Árfigyelő Price Intelligence indul...")

    price_products = build_price_products()
    validate_coverage(price_products)

    company_totals = calculate_company_totals(price_products)

    history_before = load_history()
    weekly_change = calculate_weekly_change(company_totals, history_before)

    snapshot = build_snapshot(company_totals, weekly_change)
    intelligence = build_price_intelligence(company_totals, weekly_change)
    history = update_history(company_totals)

    save_json(PRICE_PRODUCTS, price_products)
    save_json(PRICE_SNAPSHOT, snapshot)
    save_json(PRICE_INTELLIGENCE, intelligence)
    save_json(PRICE_HISTORY, history)

    print("Kész. Frissített fájlok:")
    print("-", PRICE_PRODUCTS)
    print("-", PRICE_SNAPSHOT)
    print("-", PRICE_INTELLIGENCE)
    print("-", PRICE_HISTORY)


if __name__ == "__main__":
    main()
