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
PRICE_ANALYSIS = DATA_DIR / "price-analysis.json"

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
    {"id": 2, "name": "ESL tej 1,5%", "category": "Tejtermék", "unit": "l"},
    {"id": 1, "name": "ESL tej 2,8%", "category": "Tejtermék", "unit": "l"},
    {"id": 7, "name": "Natúr joghurt", "category": "Tejtermék", "unit": "kg"},
    {"id": 10, "name": "Trappista sajt", "category": "Tejtermék", "unit": "kg"},
    {"id": 12, "name": "Vaj", "category": "Tejtermék", "unit": "kg"},
    {"id": 14, "name": "Tojás", "category": "Frissáru", "unit": "db"},
    {"id": 15, "name": "Sertéscomb", "category": "Húsáru", "unit": "kg"},
    {"id": 85, "name": "Darált sertéshús", "category": "Húsáru", "unit": "kg"},
    {"id": 18, "name": "Csirkemellfilé", "category": "Húsáru", "unit": "kg"},
    {"id": 21, "name": "Pulykamellfilé", "category": "Húsáru", "unit": "kg"},
    {"id": 28, "name": "Alma", "category": "Gyümölcs", "unit": "kg"},
    {"id": 31, "name": "Banán", "category": "Gyümölcs", "unit": "kg"},
    {"id": 32, "name": "Citrom", "category": "Gyümölcs", "unit": "kg"},
    {"id": 34, "name": "Paradicsom", "category": "Zöldség", "unit": "kg"},
    {"id": 35, "name": "Zöldpaprika", "category": "Zöldség", "unit": "kg"},
    {"id": 40, "name": "Vöröshagyma", "category": "Zöldség", "unit": "kg"},
    {"id": 41, "name": "Étkezési burgonya", "category": "Zöldség", "unit": "kg"},
    {"id": 50, "name": "Száraztészta", "category": "Alapélelmiszer", "unit": "kg"},
    {"id": 51, "name": "Étolaj", "category": "Alapélelmiszer", "unit": "l"},
    {"id": 52, "name": "Finomliszt", "category": "Alapélelmiszer", "unit": "kg"},
    {"id": 54, "name": "Kristálycukor", "category": "Alapélelmiszer", "unit": "kg"},
    {"id": 67, "name": "Ásványvíz", "category": "Ital", "unit": "l"},
    {"id": 95, "name": "Rizs", "category": "Alapélelmiszer", "unit": "kg"},
    {"id": 126, "name": "Toalettpapír", "category": "Háztartás", "unit": "db", "min_unit_amount": 40},
    {"id": 131, "name": "Folyékony mosószer", "category": "Háztartás", "unit": "l", "exclude": ["kapszula", "pods", "pod", "tabletta", "all in 1", "allin1"]}
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

    while True:
        query = urllib.parse.urlencode({
            "limit": limit,
            "offset": offset,
            "order": "unitAmount_asc"
        })

        url = f"{ARFIGYELO_BASE}/products-by-category/{category_id}?{query}"
        data = fetch_json(url)

        batch = data.get("products", [])
        count = data.get("count", 0)

        products.extend(batch)

        if not batch:
            break

        offset += limit

        if offset >= count:
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


def product_allowed(product, benchmark_item, price_data):
    product_name = str(product.get("name", "")).lower()
    unit = str(product.get("unit", "")).lower()

    expected_unit = benchmark_item.get("unit")

    if expected_unit and unit != expected_unit:
        return False

    for word in benchmark_item.get("exclude", []):
        if word.lower() in product_name:
            return False

    unit_amount = price_data.get("unit_amount")

    if unit_amount is None:
        return False

    min_unit_amount = benchmark_item.get("min_unit_amount")

    if min_unit_amount is not None and float(unit_amount) < float(min_unit_amount):
        return False

    return True


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

                if not product_allowed(product, item, price_data):
                    continue

                comparable_price = price_data["unit_amount"]

                previous = company_prices.get(company)

                if previous is None or comparable_price < previous:
                    company_prices[company] = comparable_price
                    selected_products[company] = {
                        "source_product_id": product.get("id"),
                        "source_product_name": product.get("name"),
                        "amount": price_data["amount"],
                        "unit_amount": price_data["unit_amount"],
                        "unit": product.get("unit"),
                        "unit_title": product.get("unitTitle"),
                        "packaging": product.get("packaging"),
                        "price_type": price_data["price_type"]
                    }

        result_products.append({
            "id": str(item["id"]),
            "product": item["name"],
            "category": item["category"],
            "expected_unit": item.get("unit"),
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

    if covered_items < 10 or total_hits < 30:
        raise RuntimeError(
            "Túl alacsony lefedettség. Nem írunk adatfájlokat. "
            f"Lefedett termék: {covered_items}, találat: {total_hits}."
        )

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


def calculate_price_index(price_products):
    company_scores = {company: [] for company in COMPANIES}

    for product in price_products["products"]:
        prices = product.get("prices", {})

        valid_prices = [
            float(price)
            for price in prices.values()
            if price is not None and float(price) > 0
        ]

        if len(valid_prices) < 3:
            continue

        product_average = sum(valid_prices) / len(valid_prices)

        for company in COMPANIES:
            price = prices.get(company)

            if price is None:
                continue

            company_scores[company].append((float(price) / product_average) * 100)

    result = {}

    for company, scores in company_scores.items():
        if not scores:
            result[company] = {
                "price_index": None,
                "index_coverage": 0
            }
        else:
            result[company] = {
                "price_index": round(sum(scores) / len(scores)),
                "index_coverage": len(scores)
            }

    return result


def build_price_analysis(price_products, price_index_data):
    cheapest_count = {company: 0 for company in COMPANIES}
    most_expensive_count = {company: 0 for company in COMPANIES}
    product_leaders = []
    product_spreads = []

    category_scores = {}
    category_leaders = []

    for product in price_products["products"]:
        prices = {
            company: float(price)
            for company, price in product.get("prices", {}).items()
            if price is not None and float(price) > 0
        }

        if len(prices) < 3:
            continue

        cheapest_company = min(prices, key=prices.get)
        most_expensive_company = max(prices, key=prices.get)

        cheapest_price = prices[cheapest_company]
        most_expensive_price = prices[most_expensive_company]

        average_price = sum(prices.values()) / len(prices)
        spread_pct = ((most_expensive_price - cheapest_price) / cheapest_price) * 100 if cheapest_price > 0 else None

        cheapest_count[cheapest_company] += 1
        most_expensive_count[most_expensive_company] += 1

        if spread_pct is None:
            intensity = "n.a."
        elif spread_pct <= 5:
            intensity = "erős árverseny"
        elif spread_pct <= 15:
            intensity = "közepes árverseny"
        else:
            intensity = "nagy árszórás"

        product_leaders.append({
            "product": product["product"],
            "category": product["category"],
            "cheapest_company": cheapest_company,
            "cheapest_price": round(cheapest_price, 2),
            "most_expensive_company": most_expensive_company,
            "most_expensive_price": round(most_expensive_price, 2),
            "average_price": round(average_price, 2),
            "spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
            "competition_intensity": intensity,
            "coverage": len(prices)
        })

        product_spreads.append({
            "product": product["product"],
            "category": product["category"],
            "spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
            "competition_intensity": intensity,
            "coverage": len(prices)
        })

        category = product["category"]

        if category not in category_scores:
            category_scores[category] = {company: [] for company in COMPANIES}

        for company in COMPANIES:
            price = prices.get(company)

            if price is None:
                continue

            category_scores[category][company].append((price / average_price) * 100)

    for category, scores_by_company in category_scores.items():
        category_indexes = []

        for company, scores in scores_by_company.items():
            if not scores:
                continue

            category_indexes.append({
                "company": company,
                "category_index": round(sum(scores) / len(scores)),
                "coverage": len(scores)
            })

        category_indexes.sort(key=lambda item: item["category_index"])

        category_leaders.append({
            "category": category,
            "leader": category_indexes[0]["company"] if category_indexes else None,
            "leader_index": category_indexes[0]["category_index"] if category_indexes else None,
            "ranking": category_indexes
        })

    product_leaders.sort(key=lambda item: item["spread_pct"] if item["spread_pct"] is not None else -1, reverse=True)
    product_spreads.sort(key=lambda item: item["spread_pct"] if item["spread_pct"] is not None else -1, reverse=True)

    value_scores = []

    for company in COMPANIES:
        price_index = price_index_data[company]["price_index"]

        if price_index is None:
            value_score = None
        else:
            value_score = round(200 - price_index)

        value_scores.append({
            "company": company,
            "price_index": price_index,
            "value_score": value_score,
            "index_coverage": price_index_data[company]["index_coverage"]
        })

    value_scores.sort(key=lambda item: item["value_score"] if item["value_score"] is not None else -999, reverse=True)

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "method": "product-level price leadership and spread analysis",
        "cheapest_count": [
            {"company": company, "count": cheapest_count[company]}
            for company in sorted(cheapest_count, key=cheapest_count.get, reverse=True)
        ],
        "most_expensive_count": [
            {"company": company, "count": most_expensive_count[company]}
            for company in sorted(most_expensive_count, key=most_expensive_count.get, reverse=True)
        ],
        "value_scores": value_scores,
        "category_leaders": sorted(category_leaders, key=lambda item: item["category"]),
        "product_leaders": product_leaders,
        "product_spreads": product_spreads
    }


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


def calculate_weekly_change(price_index_data, history):
    previous = get_previous_history_row(history)
    changes = []

    for company in COMPANIES:
        current = price_index_data[company]["price_index"]

        if current is None:
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

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "companies": [
            {
                "company": company,
                "basket_price_huf": company_totals[company]["basket_price_huf"],
                "covered_products": company_totals[company]["covered_products"],
                "weekly_change_pct": weekly.get(company),
                "stability_score": None,
                "promotion_intensity": None
            }
            for company in COMPANIES
        ]
    }


def build_price_intelligence(company_totals, price_index_data, weekly_change):
    ranking = []

    for company in COMPANIES:
        ranking.append({
            "company": company,
            "price_index": price_index_data[company]["price_index"],
            "basket_price_huf": company_totals[company]["basket_price_huf"],
            "covered_products": company_totals[company]["covered_products"],
            "index_coverage": price_index_data[company]["index_coverage"]
        })

    ranking.sort(
        key=lambda item: item["price_index"] if item["price_index"] is not None else 9999
    )

    return {
        "updated_at": utc_now(),
        "source": "GVH Árfigyelő API",
        "status": "ok",
        "method": "unit-filtered product-level relative price index",
        "ranking": ranking,
        "weekly_change": weekly_change
    }


def update_history(price_index_data):
    history = load_history()

    row = {
        "date": today()
    }

    for company in COMPANIES:
        row[company] = price_index_data[company]["price_index"]

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
    price_index_data = calculate_price_index(price_products)

    history_before = load_history()
    weekly_change = calculate_weekly_change(price_index_data, history_before)

    snapshot = build_snapshot(company_totals, weekly_change)
    intelligence = build_price_intelligence(company_totals, price_index_data, weekly_change)
    analysis = build_price_analysis(price_products, price_index_data)
    history = update_history(price_index_data)

    save_json(PRICE_PRODUCTS, price_products)
    save_json(PRICE_SNAPSHOT, snapshot)
    save_json(PRICE_INTELLIGENCE, intelligence)
    save_json(PRICE_ANALYSIS, analysis)
    save_json(PRICE_HISTORY, history)

    print("Kész. Frissített fájlok:")
    print("-", PRICE_PRODUCTS)
    print("-", PRICE_SNAPSHOT)
    print("-", PRICE_INTELLIGENCE)
    print("-", PRICE_ANALYSIS)
    print("-", PRICE_HISTORY)


if __name__ == "__main__":
    main()
