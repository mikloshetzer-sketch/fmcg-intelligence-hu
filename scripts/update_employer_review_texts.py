#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Intelligence Hungary
Employer Review Text Collector

Cél:
- Publikus munkáltatói értékelések szöveges mintáinak kigyűjtése.
- Személyes adatok eltávolítása.
- Téma- és hangulatelemzés egyszerű kulcsszavas logikával.
- Kimenet mentése:
  docs/data/employer-review-texts.json

Fontos:
- Csak publikus, jogszerűen hozzáférhető oldalakhoz használd.
- Ne kerüljön mentésre név, e-mail, telefonszám vagy más személyes adat.
- A script nem tör fel oldalt, nem lép be fiókba, nem kerül meg védelmet.
"""

import json
import re
import time
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_FILE = DATA_DIR / "employer-review-texts.json"
SOURCE_REVIEW_FILE = DATA_DIR / "employer-reviews.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 20
SLEEP_MIN = 2.0
SLEEP_MAX = 5.0


COMPANIES = [
    {
        "company": "Auchan",
        "search_names": ["Auchan", "Auchan Magyarország"],
    },
    {
        "company": "Lidl",
        "search_names": ["Lidl", "Lidl Magyarország"],
    },
    {
        "company": "Aldi",
        "search_names": ["ALDI", "ALDI Magyarország"],
    },
    {
        "company": "Penny",
        "search_names": ["Penny", "PENNY Magyarország"],
    },
    {
        "company": "Spar",
        "search_names": ["SPAR", "SPAR Magyarország"],
    },
    {
        "company": "Tesco",
        "search_names": ["Tesco", "Tesco Magyarország"],
    },
]


# Itt bővíthető később konkrét, ellenőrzött publikus forrásoldalakkal.
# A direct_urls mezőbe olyan oldalt tegyél, ahol valóban publikus értékelések vannak.
REVIEW_SOURCE_CONFIG = {
    "profession": {
        "enabled": True,
        "base": "https://www.profession.hu",
        "direct_urls": {
            "Auchan": [],
            "Lidl": [],
            "Aldi": [],
            "Penny": [],
            "Spar": [],
            "Tesco": [],
        },
    },
    "manual_public_sources": {
        "enabled": True,
        "direct_urls": {
            "Auchan": [],
            "Lidl": [],
            "Aldi": [],
            "Penny": [],
            "Spar": [],
            "Tesco": [],
        },
    },
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "alacsony bér", "kevés pénz", "órabér",
        "jövedelem", "kereset", "pénz", "fizetnek"
    ],
    "juttatások": [
        "juttatás", "cafeteria", "bónusz", "kedvezmény", "étkezési",
        "utalvány", "prémium", "jutalom"
    ],
    "munkaterhelés": [
        "sok munka", "leterhel", "túlterhel", "hajtás", "fárasztó",
        "munka mennyisége", "kevés ember", "létszámhiány", "tempó"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "rugalmas",
        "munkaidő", "éjszaka", "vasárnap"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "irányítás", "kommunikáció",
        "vezetőség", "felettes", "vezetői"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "hangulat",
        "segítőkész", "összetartás"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "képzés", "betanítás",
        "tanulás", "lehetőség"
    ],
    "munkahelyi légkör": [
        "légkör", "stressz", "megbecsülés", "tisztelet", "hangulat",
        "konfliktus", "nyomás"
    ],
}


POSITIVE_WORDS = [
    "jó", "pozitív", "korrekt", "segítőkész", "stabil", "rugalmas",
    "barátságos", "megbecsül", "támogató", "fejlődés", "lehetőség",
    "biztos", "kiszámítható", "elégedett"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "leterhel", "létszámhiány", "fárasztó", "probléma", "gyenge",
    "elégedetlen", "nyomás", "konfliktus", "kaotikus"
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def remove_personal_data(text: str) -> str:
    text = text or ""

    # E-mail címek eltávolítása
    text = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "[email eltávolítva]",
        text,
    )

    # Telefonszám jellegű minták eltávolítása
    text = re.sub(
        r"(\+36|06)?[\s\-]?\(?\d{1,2}\)?[\s\-]?\d{3}[\s\-]?\d{3,4}",
        "[telefonszám eltávolítva]",
        text,
    )

    # Teljes nevek durva kiszűrése: két nagybetűs szó egymás után
    text = re.sub(
        r"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+ "
        r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+\b",
        "[név eltávolítva]",
        text,
    )

    return clean_whitespace(text)


def normalize_quote(text: str, max_len: int = 260) -> str:
    text = remove_personal_data(text)
    text = clean_whitespace(text)

    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."

    return text


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in lower:
                score += 1
        scores[topic] = score

    best_topic = max(scores, key=scores.get)

    if scores[best_topic] == 0:
        return "általános munkáltatói tapasztalat"

    return best_topic


def classify_sentiment(text: str) -> str:
    lower = text.lower()

    positive = sum(1 for word in POSITIVE_WORDS if word in lower)
    negative = sum(1 for word in NEGATIVE_WORDS if word in lower)

    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def make_text_hash(text: str) -> str:
    import hashlib
    clean = clean_whitespace(text.lower())
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]


def is_valid_review_text(text: str) -> bool:
    text = clean_whitespace(text)

    if len(text) < 35:
        return False

    if len(text.split()) < 6:
        return False

    banned_fragments = [
        "cookie",
        "javascript",
        "adatvédelmi",
        "bejelentkezés",
        "regisztráció",
        "elfogadom",
        "hirdetés",
    ]

    lower = text.lower()
    if any(fragment in lower for fragment in banned_fragments):
        return False

    return True


def fetch_html(url: str) -> Optional[str]:
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None
        return response.text
    except Exception:
        return None


def extract_candidate_texts_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    candidates = []

    selectors = [
        "article",
        ".review",
        ".reviews",
        ".rating",
        ".comment",
        ".opinion",
        ".description",
        "p",
        "li",
    ]

    seen = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_whitespace(node.get_text(" ", strip=True))

            if not is_valid_review_text(text):
                continue

            text_hash = make_text_hash(text)
            if text_hash in seen:
                continue

            seen.add(text_hash)
            candidates.append(text)

    return candidates


def collect_from_direct_urls(company: str, source_name: str, urls: List[str]) -> List[Dict[str, Any]]:
    collected = []

    for url in urls:
        html = fetch_html(url)

        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        if not html:
            continue

        texts = extract_candidate_texts_from_html(html)

        for text in texts:
            quote = normalize_quote(text)

            if not is_valid_review_text(quote):
                continue

            collected.append({
                "id": make_text_hash(company + source_name + quote),
                "company": company,
                "source": source_name,
                "source_url": url,
                "date_collected": now_iso(),
                "role": None,
                "topic": classify_topic(quote),
                "sentiment": classify_sentiment(quote),
                "quote": quote,
                "length": len(quote),
                "confidence": "medium",
                "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak."
            })

    return collected


def collect_company_reviews(company: str) -> List[Dict[str, Any]]:
    all_items = []

    for source_name, config in REVIEW_SOURCE_CONFIG.items():
        if not config.get("enabled", False):
            continue

        direct_urls = config.get("direct_urls", {}).get(company, [])
        if not direct_urls:
            continue

        items = collect_from_direct_urls(
            company=company,
            source_name=source_name,
            urls=direct_urls,
        )
        all_items.extend(items)

    return all_items


def merge_with_existing(existing: Dict[str, Any], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    old_items = existing.get("items", [])
    merged_by_id = {}

    for item in old_items:
        item_id = item.get("id")
        if item_id:
            merged_by_id[item_id] = item

    for item in new_items:
        item_id = item.get("id")
        if item_id:
            merged_by_id[item_id] = item

    return list(merged_by_id.values())


def summarize_company(company: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    company_items = [x for x in items if x.get("company") == company]

    topic_counts: Dict[str, int] = {}
    sentiment_counts = {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    }

    for item in company_items:
        topic = item.get("topic") or "általános"
        sentiment = item.get("sentiment") or "neutral"

        topic_counts[topic] = topic_counts.get(topic, 0) + 1

        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        else:
            sentiment_counts["neutral"] += 1

    dominant_topics = sorted(
        topic_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    sample_quotes = company_items[:5]

    return {
        "company": company,
        "review_text_count": len(company_items),
        "dominant_topics": [
            {"topic": topic, "count": count}
            for topic, count in dominant_topics[:6]
        ],
        "sentiment_counts": sentiment_counts,
        "sample_quotes": sample_quotes,
    }


def build_output(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    summaries = []

    for company_config in COMPANIES:
        company = company_config["company"]
        summaries.append(summarize_company(company, items))

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "source_type": "public_osint_employee_reviews",
        "method": "direct_public_url_text_extraction_keyword_topic_sentiment_v1",
        "important_note": (
            "A szöveges dolgozói értékelések publikus forrásokból származó, "
            "automatikusan tisztított minták. Az eredmény nem reprezentatív közvélemény-kutatás, "
            "hanem OSINT jellegű reputációs jelzés."
        ),
        "privacy_note": (
            "A script eltávolítja az e-mail címeket, telefonszámokat és felismerhető teljes neveket. "
            "A kimenetbe nem szabad személyes adatot menteni."
        ),
        "companies": summaries,
        "items": items,
    }


def create_empty_template_if_no_sources() -> Dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "status": "no_sources_configured",
        "source_type": "public_osint_employee_reviews",
        "method": "direct_public_url_text_extraction_keyword_topic_sentiment_v1",
        "important_note": (
            "Még nincs beállítva konkrét publikus értékelési URL. "
            "A REVIEW_SOURCE_CONFIG direct_urls mezőibe kell felvenni a vizsgált oldalakat."
        ),
        "privacy_note": (
            "Csak személyes adatot nem tartalmazó, publikus szöveges mintákat szabad menteni."
        ),
        "companies": [
            {
                "company": company["company"],
                "review_text_count": 0,
                "dominant_topics": [],
                "sentiment_counts": {
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0,
                },
                "sample_quotes": [],
            }
            for company in COMPANIES
        ],
        "items": [],
    }


def has_any_configured_url() -> bool:
    for _, config in REVIEW_SOURCE_CONFIG.items():
        if not config.get("enabled", False):
            continue

        direct_urls = config.get("direct_urls", {})

        for _, urls in direct_urls.items():
            if urls:
                return True

    return False


def main() -> None:
    print("Employer review text collector started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_json(OUTPUT_FILE, fallback={})

    if not has_any_configured_url():
        output = create_empty_template_if_no_sources()
        save_json(OUTPUT_FILE, output)
        print(f"No source URLs configured. Empty template saved: {OUTPUT_FILE}")
        return

    new_items = []

    for company_config in COMPANIES:
        company = company_config["company"]
        print(f"Collecting review texts for: {company}")

        company_items = collect_company_reviews(company)
        print(f"  collected: {len(company_items)}")

        new_items.extend(company_items)

    merged_items = merge_with_existing(existing, new_items)

    output = build_output(merged_items)
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Total review text items: {len(merged_items)}")


if __name__ == "__main__":
    main()
