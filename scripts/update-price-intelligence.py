import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

SNAPSHOT = BASE / "docs" / "data" / "price-snapshot.json"
HISTORY = BASE / "docs" / "data" / "price-history.json"

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

def append_history():

    snapshot = load_json(SNAPSHOT)
    history = load_json(HISTORY)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    existing_dates = {
        item["date"]
        for item in history["history"]
    }

    if today in existing_dates:

        print("History already updated.")

        return

    row = {
        "date": today
    }

    for company in snapshot["companies"]:

        row[company["company"]] = company["basket_price_huf"]

    history["history"].append(row)

    history["updated_at"] = datetime.utcnow().isoformat()

    save_json(HISTORY, history)

    print("History updated.")

if __name__ == "__main__":

    append_history()
