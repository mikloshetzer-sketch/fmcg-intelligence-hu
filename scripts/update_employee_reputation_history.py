#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Employee Reputation History Builder v1

Input:
- docs/data/employee-reputation-index.json

Outputs:
- docs/data/employee-reputation-history.json
- docs/data/employee-reputation-history/YYYY-MM-DD.json

Feladat:
- Az aktuális Employee Reputation Index pillanatképet idősorba menti.
- Nem írja felül a meglévő múltbeli adatokat.
- Cégenként napi egy rekordot tart meg.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

INPUT_FILE = DATA_DIR / "employee-reputation-index.json"
HISTORY_FILE = DATA_DIR / "employee-reputation-history.json"
HISTORY_DIR = DATA_DIR / "employee-reputation-history"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def get_companies(snapshot):
    companies = snapshot.get("companies", [])

    if isinstance(companies, list):
        return companies

    return []


def build_daily_snapshot(snapshot):
    date = today_str()
    updated_at = snapshot.get("updated_at") or now_iso()

    rows = []

    for company in get_companies(snapshot):
        rows.append({
            "date": date,
            "updated_at": updated_at,
            "company_id": company.get("company_id") or company.get("id"),
            "company": company.get("company"),
            "employee_reputation_index": company.get("employee_reputation_index"),
            "index_level": company.get("index_level"),
            "review_count": company.get("review_count"),
            "positive_pct": company.get("positive_pct"),
            "negative_pct": company.get("negative_pct"),
            "neutral_pct": company.get("neutral_pct"),
            "salary_risk_score": (
                company.get("salary_risk", {}).get("score")
                if isinstance(company.get("salary_risk"), dict)
                else None
            ),
            "stress_risk_score": (
                company.get("stress_risk", {}).get("score")
                if isinstance(company.get("stress_risk"), dict)
                else None
            ),
            "leadership_risk_score": (
                company.get("leadership_risk", {}).get("score")
                if isinstance(company.get("leadership_risk"), dict)
                else None
            ),
            "team_strength_score": (
                company.get("team_strength", {}).get("score")
                if isinstance(company.get("team_strength"), dict)
                else None
            ),
        })

    return {
        "date": date,
        "updated_at": now_iso(),
        "source_updated_at": updated_at,
        "status": "ok" if rows else "no_rows",
        "rows": rows,
    }


def merge_history(existing, daily_snapshot):
    history_rows = []

    if isinstance(existing, dict):
        history_rows = existing.get("rows", [])
    elif isinstance(existing, list):
        history_rows = existing

    merged = {}

    for row in history_rows:
        key = (
            row.get("date"),
            row.get("company_id") or row.get("company"),
        )
        merged[key] = row

    for row in daily_snapshot.get("rows", []):
        key = (
            row.get("date"),
            row.get("company_id") or row.get("company"),
        )
        merged[key] = row

    rows = sorted(
        merged.values(),
        key=lambda row: (
            row.get("date", ""),
            row.get("company", ""),
        )
    )

    return {
        "updated_at": now_iso(),
        "status": "ok" if rows else "no_rows",
        "method": "employee_reputation_history_v1_daily_snapshot",
        "input_file": "docs/data/employee-reputation-index.json",
        "important_note": (
            "Ez az Employee Reputation Index idősoros mentése. "
            "Cégenként és naponként egy rekordot tartalmaz. "
            "A trend 3-4 eltérő dátum után értelmezhető."
        ),
        "rows": rows,
    }


def main():
    print("Employee Reputation History Builder started.")

    snapshot = load_json(INPUT_FILE, {})
    daily_snapshot = build_daily_snapshot(snapshot)

    save_json(HISTORY_DIR / f"{today_str()}.json", daily_snapshot)

    existing_history = load_json(HISTORY_FILE, {"rows": []})
    merged_history = merge_history(existing_history, daily_snapshot)

    save_json(HISTORY_FILE, merged_history)

    print(f"Saved: {HISTORY_FILE}")
    print(f"Saved: {HISTORY_DIR / (today_str() + '.json')}")
    print(f"Rows today: {len(daily_snapshot.get('rows', []))}")
    print(f"Rows total: {len(merged_history.get('rows', []))}")


if __name__ == "__main__":
    main()
