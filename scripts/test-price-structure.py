import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

OUTPUT = BASE / "docs" / "data" / "price-structure.json"

TEST_ID = 1


def fetch_json(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def main():

    url = (
        f"https://arfigyelo.gvh.hu/api/"
        f"products-by-category/{TEST_ID}"
        f"?limit=1&offset=0"
    )

    data = fetch_json(url)

    product = data["products"][0]

    result = {

        "product_name": product.get("name"),

        "unit": product.get("unit"),

        "packaging": product.get("packaging"),

        "chain_store_sample":

        product.get(
            "pricesOfChainStores",
            []
        )[:2]

    }

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("Kész")


if __name__ == "__main__":

    main()
