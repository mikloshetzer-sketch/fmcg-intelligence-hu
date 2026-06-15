import json
import urllib.request
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
OUTPUT = BASE / "docs" / "data" / "arfigyelo-category-discovery.json"

URLS_TO_TEST = [
    "https://arfigyelo.gvh.hu/api/categories",
    "https://arfigyelo.gvh.hu/api/product-categories",
    "https://arfigyelo.gvh.hu/api/category",
    "https://arfigyelo.gvh.hu/api/categories/tree",
    "https://arfigyelo.gvh.hu/api/menu",
    "https://arfigyelo.gvh.hu/api/filters",
]


def utc_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def fetch_raw(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8", errors="replace")
        return response.status, content_type, raw


def try_parse_json(raw):
    try:
        return json.loads(raw)
    except Exception:
        return None


def summarize(data):
    if isinstance(data, dict):
        return {
            "type": "dict",
            "keys": list(data.keys()),
            "sample": data
        }

    if isinstance(data, list):
        return {
            "type": "list",
            "length": len(data),
            "sample": data[:20]
        }

    return {
        "type": type(data).__name__,
        "sample": data
    }


def main():
    results = []

    for url in URLS_TO_TEST:
        print("Testing:", url)

        try:
            status, content_type, raw = fetch_raw(url)
            parsed = try_parse_json(raw)

            item = {
                "url": url,
                "status": status,
                "content_type": content_type,
                "json": parsed is not None
            }

            if parsed is not None:
                item["summary"] = summarize(parsed)
            else:
                item["raw_preview"] = raw[:1000]

            results.append(item)

        except Exception as error:
            results.append({
                "url": url,
                "status": "error",
                "error": str(error)
            })

    output = {
        "updated_at": utc_now(),
        "results": results
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Mentve:", OUTPUT)


if __name__ == "__main__":
    main()
