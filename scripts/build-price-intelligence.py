import json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]

PRODUCTS = BASE / "docs" / "data" / "price-products.json"
OUTPUT = BASE / "docs" / "data" / "price-intelligence.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def build_price_intelligence():

    source = load_json(PRODUCTS)

    companies = [
        "ALDI",
        "Auchan",
        "Lidl",
        "Penny",
        "SPAR",
        "Tesco"
    ]

    company_totals = {}

    for company in companies:
        company_totals[company] = 0

    for product in source["products"]:

        for company, price in product["prices"].items():

            company_totals[company] += price

    average = sum(company_totals.values()) / len(company_totals)

    ranking = []

    for company, total in company_totals.items():

        index = round((total / average) * 100)

        ranking.append({
            "company": company,
            "price_index": index
        })

    ranking.sort(key=lambda x: x["price_index"])

    result = {
        "updated_at": datetime.utcnow().isoformat(),

        "ranking": ranking,

        "weekly_change": []
    }

    save_json(OUTPUT, result)

    print("Price Intelligence updated")


if __name__ == "__main__":

    build_price_intelligence()
