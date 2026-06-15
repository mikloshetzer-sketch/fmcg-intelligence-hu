import json
import urllib.request
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]

OUTPUT = BASE / "docs" / "data" / "arfigyelo-api-inspection.json"

TEST_URL = "https://arfigyelo.gvh.hu/api/products-by-category/2046?limit=24&offset=0&order=unitAmount_asc"


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def inspect_arfigyelo():
    print("GVH Árfigyelő API teszt indul...")
    print("URL:", TEST_URL)

    try:
        data = fetch_json(TEST_URL)

        inspection = {
            "updated_at": datetime.utcnow().isoformat(),
            "status": "ok",
            "tested_url": TEST_URL,
            "root_type": type(data).__name__,
            "top_level_keys": list(data.keys()) if isinstance(data, dict) else [],
            "sample": data
        }

        save_json(OUTPUT, inspection)

        print("Sikeres lekérés.")
        print("Eredmény mentve ide:")
        print(OUTPUT)

    except Exception as error:
        inspection = {
            "updated_at": datetime.utcnow().isoformat(),
            "status": "error",
            "tested_url": TEST_URL,
            "error": str(error)
        }

        save_json(OUTPUT, inspection)

        print("Hiba történt:")
        print(error)
        print("Hibajelentés mentve ide:")
        print(OUTPUT)


if __name__ == "__main__":
    inspect_arfigyelo()
