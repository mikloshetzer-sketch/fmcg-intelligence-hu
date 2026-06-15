import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

OUTPUT = BASE / "docs" / "data" / "arfigyelo-id-test.json"

TEST_IDS = [
    1,
    2,
    7,
    10,
    12,
    14,
    18,
    31,
    41
]


def fetch_url(url):

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

    results = []

    for test_id in TEST_IDS:

        url = (
            f"https://arfigyelo.gvh.hu/api/"
            f"products-by-category/{test_id}"
            f"?limit=5&offset=0"
        )

        print(f"Teszt: {test_id}")

        try:

            data = fetch_url(url)

            results.append({

                "id": test_id,

                "count": data.get("count"),

                "products_found": len(
                    data.get("products", [])
                ),

                "success": True

            })

        except Exception as error:

            results.append({

                "id": test_id,

                "success": False,

                "error": str(error)

            })

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            results,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("Kész.")


if __name__ == "__main__":

    main()
