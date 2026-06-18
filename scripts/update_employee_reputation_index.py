#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Employee Reputation Index Generator v1

Bemenet:
docs/data/employer-review-texts.json

Kimenet:
docs/data/employee-reputation-index.json

Cél:
- A dolgozói véleményekből cégenként összesített mutatók számítása.
- Employee Reputation Index 0-100 skálán.
- Pozitív / semleges / negatív arány.
- Tématerületi kockázatok:
  - bérezés
  - munkaterhelés
  - vezetés
  - csapat
  - munkaidő / beosztás
  - munkahelyi légkör
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

INPUT_FILE = DATA_DIR / "employer-review-texts.json"
OUTPUT_FILE = DATA_DIR / "employee-reputation-index.json"


COMPANIES = [
    "Auchan",
    "Lidl",
    "Aldi",
    "Penny",
    "Spar",
    "Tesco",
]


NEGATIVE_TERMS = [
    "rossz",
    "alacsony",
    "kevés",
    "stressz",
    "stresszes",
    "túlóra",
    "létszámhiány",
    "fárasztó",
    "nem ajánlom",
    "felmondtam",
    "problémás",
    "tervezhetetlen",
    "fejetlenség",
    "kihasználnak",
    "gusztustalan",
    "rossz fizetés",
    "alacsony bér",
    "nem megértő",
    "hajtás",
    "nagy elvárás",
    "monoton",
]


POSITIVE_TERMS = [
    "jó",
    "korrekt",
    "pozitív",
    "segítőkész",
    "stabil",
    "rugalmas",
    "elégedett",
    "ajánlom",
    "jó csapat",
    "összetartó",
    "barátságos",
    "fejlődés",
    "lehetőség",
    "kellemes",
    "motiváló",
    "remek",
    "elfogadható",
    "kedves",
    "támogató",
]


TOPIC_GROUPS = {
    "salary": [
        "bérezés",
    ],
    "workload": [
        "munkaterhelés",
    ],
    "leadership": [
        "vezetés",
    ],
    "team": [
        "csapat",
    ],
    "schedule": [
        "beosztás",
    ],
    "workplace_climate": [
        "munkahelyi légkör",
    ],
    "benefits": [
        "juttatások",
    ],
    "development": [
        "előrelépés",
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def clamp(value: float, minimum: int = 0, maximum: int = 100) -> int:
    return int(max(minimum, min(maximum, round(value))))


def pct(part: int, total: int) -> int:
    if total <= 0:
        return 0

    return round((part / total) * 100)


def text_score(text: str) -> Dict[str, int]:
    lower = (text or "").lower()

    positive_hits = sum(1 for word in POSITIVE_TERMS if word in lower)
    negative_hits = sum(1 for word in NEGATIVE_TERMS if word in lower)

    return {
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
    }


def classify_risk_level(score: int) -> str:
    if score >= 70:
        return "magas"

    if score >= 45:
        return "közepes"

    return "alacsony"


def classify_index_level(score: int) -> str:
    if score >= 70:
        return "kedvező"

    if score >= 50:
        return "vegyes"

    return "kockázatos"


def get_company_items(items: List[Dict[str, Any]], company: str) -> List[Dict[str, Any]]:
    return [
        item for item in items
        if item.get("company") == company
    ]


def topic_count(company_items: List[Dict[str, Any]], topic_names: List[str]) -> int:
    return sum(
        1 for item in company_items
        if item.get("topic") in topic_names
    )


def build_topic_distribution(company_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}

    for item in company_items:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        counts[topic] = counts.get(topic, 0) + 1

    return [
        {
            "topic": topic,
            "count": count,
            "share_pct": pct(count, len(company_items)),
        }
        for topic, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    ]


def calculate_dimension_scores(company_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(company_items)

    scores: Dict[str, Any] = {}

    for dimension, topics in TOPIC_GROUPS.items():
        count = topic_count(company_items, topics)
        share = pct(count, total)

        related_items = [
            item for item in company_items
            if item.get("topic") in topics
        ]

        negative_related = sum(
            1 for item in related_items
            if item.get("sentiment") == "negative"
        )

        positive_related = sum(
            1 for item in related_items
            if item.get("sentiment") == "positive"
        )

        risk = 0

        if related_items:
            risk = clamp(
                35
                + share * 0.45
                + pct(negative_related, len(related_items)) * 0.45
                - pct(positive_related, len(related_items)) * 0.20
            )

        scores[dimension] = {
            "mention_count": count,
            "mention_share_pct": share,
            "positive_count": positive_related,
            "negative_count": negative_related,
            "risk_score": risk,
            "risk_level": classify_risk_level(risk),
        }

    return scores


def calculate_company_index(company: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    company_items = get_company_items(items, company)
    total = len(company_items)

    positive = sum(1 for item in company_items if item.get("sentiment") == "positive")
    neutral = sum(1 for item in company_items if item.get("sentiment") == "neutral")
    negative = sum(1 for item in company_items if item.get("sentiment") == "negative")

    text_positive_hits = 0
    text_negative_hits = 0

    for item in company_items:
        quote = item.get("quote", "")
        scores = text_score(quote)
        text_positive_hits += scores["positive_hits"]
        text_negative_hits += scores["negative_hits"]

    positive_pct = pct(positive, total)
    neutral_pct = pct(neutral, total)
    negative_pct = pct(negative, total)

    raw_index = 50

    if total > 0:
        raw_index = (
            50
            + positive_pct * 0.45
            - negative_pct * 0.55
            + min(text_positive_hits, 25) * 0.8
            - min(text_negative_hits, 25) * 0.9
        )

    employee_reputation_index = clamp(raw_index)

    dimension_scores = calculate_dimension_scores(company_items)

    stress_risk = max(
        dimension_scores["workload"]["risk_score"],
        dimension_scores["workplace_climate"]["risk_score"],
        dimension_scores["schedule"]["risk_score"],
    )

    salary_risk = dimension_scores["salary"]["risk_score"]
    leadership_risk = dimension_scores["leadership"]["risk_score"]
    team_risk = dimension_scores["team"]["risk_score"]

    team_strength = clamp(
        100 - team_risk + dimension_scores["team"]["mention_share_pct"] * 0.3
    )

    source_counts: Dict[str, int] = {}

    for item in company_items:
        source = item.get("source", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    source_distribution = [
        {
            "source": source,
            "count": count,
            "share_pct": pct(count, total),
        }
        for source, count in sorted(source_counts.items(), key=lambda pair: pair[1], reverse=True)
    ]

    return {
        "company": company,
        "review_count": total,
        "employee_reputation_index": employee_reputation_index,
        "index_level": classify_index_level(employee_reputation_index),
        "positive_pct": positive_pct,
        "neutral_pct": neutral_pct,
        "negative_pct": negative_pct,
        "positive_count": positive,
        "neutral_count": neutral,
        "negative_count": negative,
        "stress_risk": {
            "score": stress_risk,
            "level": classify_risk_level(stress_risk),
        },
        "salary_risk": {
            "score": salary_risk,
            "level": classify_risk_level(salary_risk),
        },
        "leadership_risk": {
            "score": leadership_risk,
            "level": classify_risk_level(leadership_risk),
        },
        "team_strength": {
            "score": team_strength,
            "level": classify_index_level(team_strength),
        },
        "dimension_scores": dimension_scores,
        "topic_distribution": build_topic_distribution(company_items),
        "source_distribution": source_distribution,
        "sample_quotes": company_items[:5],
    }


def build_output(input_data: Dict[str, Any]) -> Dict[str, Any]:
    items = input_data.get("items", [])

    companies = [
        calculate_company_index(company, items)
        for company in COMPANIES
    ]

    ranked = sorted(
        companies,
        key=lambda item: item.get("employee_reputation_index", 0),
        reverse=True,
    )

    return {
        "updated_at": now_iso(),
        "status": "ok" if items else "no_review_items_found",
        "source_file": "docs/data/employer-review-texts.json",
        "method": "employee_reputation_index_v1_keyword_and_sentiment_based",
        "important_note": (
            "Az Employee Reputation Index nem reprezentatív dolgozói kutatás. "
            "Publikus OSINT jellegű dolgozói véleményekből számított irányjelző mutató. "
            "A magasabb érték kedvezőbb munkáltatói percepciót jelez, az egyes kockázati mutatók "
            "pedig azt jelzik, hogy mely témákban jelennek meg gyakrabban negatív vagy problémás minták."
        ),
        "companies": companies,
        "ranking": [
            {
                "rank": index + 1,
                "company": item["company"],
                "employee_reputation_index": item["employee_reputation_index"],
                "index_level": item["index_level"],
                "review_count": item["review_count"],
                "positive_pct": item["positive_pct"],
                "negative_pct": item["negative_pct"],
            }
            for index, item in enumerate(ranked)
        ],
    }


def main() -> None:
    print("Employee Reputation Index Generator started.")

    input_data = load_json(INPUT_FILE, fallback={})
    output = build_output(input_data)

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Status: {output['status']}")


if __name__ == "__main__":
    main()
