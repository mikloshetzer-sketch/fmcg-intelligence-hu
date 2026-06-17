#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Intelligence Hungary
Employer Review Text Collector

Cél:
- Publikus munkáltatói vélemények szöveges kigyűjtése.
- Cégenkénti témázás és egyszerű hangulatelemzés.
- Személyes adatok automatikus eltávolítása.
- Kimenet:
  docs/data/employer-review-texts.json

Fontos:
- Csak publikus, jogszerűen hozzáférhető oldalakat használj.
- Ne használj belépést, fiókot, cookie-t, zárt oldalt vagy tiltott scrapinget.
- A direct_urls mezőbe kézzel kell betenni a publikus véleményoldalakat.
"""

import json
import re
import time
import random
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_FILE = DATA_DIR / "employer-review-texts.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 25
SLEEP_MIN = 2.0
SLEEP_MAX = 5.0
MAX_QUOTES_PER_COMPANY = 20
MAX_QUOTE_LENGTH = 320


COMPANIES = [
    "Auchan",
    "Lidl",
    "Aldi",
    "Penny",
    "Spar",
    "Tesco",
]


REVIEW_SOURCE_CONFIG = {
    "manual_public_sources": {
        "enabled": True,
        "direct_urls": {
            "Auchan": [
                # Ide jöhetnek az Auchan publikus munkáltatói véleményoldalai.
                # Példa:
                # "https://www.example.hu/auchan-velemenyek"
            ],
            "Lidl": [
                # Ide jöhetnek a Lidl publikus munkáltatói véleményoldalai.
            ],
            "Aldi": [
                # Ide jöhetnek az Aldi publikus munkáltatói véleményoldalai.
            ],
            "Penny": [
                # Ide jöhetnek a Penny publikus munkáltatói véleményoldalai.
            ],
            "Spar": [
                # Ide jöhetnek a SPAR publikus munkáltatói véleményoldalai.
            ],
            "Tesco": [
                # Ide jöhetnek a Tesco publikus munkáltatói véleményoldalai.
            ],
        },
    }
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "bérezés", "órabér", "kereset", "jövedelem",
        "pénz", "alulfizetett", "keveset fizet", "nettó", "bruttó"
    ],
    "juttatások": [
        "juttatás", "cafeteria", "bónusz", "prémium", "kedvezmény",
        "utalvány", "jutalom", "dolgozói kedvezmény"
    ],
    "munkaterhelés": [
        "sok munka", "leterhel", "túlterhel", "hajtás", "fárasztó",
        "kevés ember", "létszámhiány", "tempó", "pörgés", "nehéz munka"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "munkaidő",
        "vasárnap", "éjszaka", "rugalmas", "szabadnap"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "vezetőség", "felettes",
        "irányítás", "kommunikáció", "vezetői", "boltvezető"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "segítőkész",
        "összetartás", "jó hangulat", "barátságos"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "képzés", "betanítás",
        "tanulás", "lehetőség", "előmenetel"
    ],
    "munkahelyi légkör": [
        "légkör", "stressz", "megbecsülés", "tisztelet", "hangulat",
        "konfliktus", "nyomás", "kiégés", "mérgező"
    ],
}


POSITIVE_WORDS = [
    "jó", "pozitív", "korrekt", "segítőkész", "stabil", "rugalmas",
    "barátságos", "megbecsül", "támogató", "fejlődés", "lehetőség",
    "biztos", "kiszámítható", "elégedett", "szeretek", "ajánlom"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "leterhel", "létszámhiány", "fárasztó", "probléma", "gyenge",
    "elégedetlen", "nyomás", "konfliktus", "kaotikus", "nem ajánlom"
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def text_hash(text: str) -> str:
    normalized = clean_whitespace(text.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def remove_personal_data(text: str) -> str:
    text = text or ""

    text = re.sub(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "[email eltávolítva]",
        text,
    )

    text = re.sub(
        r"(\+36|06)?[\s\-]?\(?\d{1,2}\)?[\s\-]?\d{3}[\s\-]?\d{3,4}",
        "[telefonszám eltávolítva]",
        text,
    )

    text = re.sub(
        r"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}\s+"
        r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}\b",
        "[név eltávolítva]",
        text,
    )

    return clean_whitespace(text)


def normalize_quote(text: str) -> str:
    text = remove_personal_data(text)
    text = clean_whitespace(text)

    if len(text) > MAX_QUOTE_LENGTH:
        text = text[:MAX_QUOTE_LENGTH].rsplit(" ", 1)[0] + "..."

    return text


def is_probably_review_text(text: str) -> bool:
    text = clean_whitespace(text)

    if len(text) < 45:
        return False

    if len(text.split()) < 7:
        return False

    lower = text.lower()

    blocked = [
        "cookie",
        "javascript",
        "adatvédelmi",
        "bejelentkezés",
        "regisztráció",
        "elfogadom",
        "hirdetés",
        "newsletter",
        "feliratkozás",
        "összes állás",
        "állások mentése",
        "keresés mentése",
    ]

    if any(word in lower for word in blocked):
        return False

    review_signals = [
        "munka",
        "dolgozó",
        "munkatárs",
        "kolléga",
        "fizetés",
        "vezető",
        "beosztás",
        "műszak",
        "csapat",
        "munkahely",
        "tapasztalat",
        "ajánlom",
        "nem ajánlom",
    ]

    return any(signal in lower for signal in review_signals)


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores: Dict[str, int] = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(1 for keyword in keywords if keyword in lower)

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


def fetch_html(url: str) -> Optional[str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"  skipped {url} status={response.status_code}")
            return None

        return response.text

    except Exception as error:
        print(f"  fetch failed {url}: {error}")
        return None


def extract_text_blocks(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    selectors = [
        "article",
        ".review",
        ".reviews",
        ".comment",
        ".opinion",
        ".rating",
        ".description",
        ".content",
        "[class*='review']",
        "[class*='comment']",
        "[class*='opinion']",
        "p",
        "li",
    ]

    texts: List[str] = []
    seen = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_whitespace(node.get_text(" ", strip=True))

            if not is_probably_review_text(text):
                continue

            normalized = normalize_quote(text)
            item_hash = text_hash(normalized)

            if item_hash in seen:
                continue

            seen.add(item_hash)
            texts.append(normalized)

    return texts


def collect_from_urls(company: str, source_name: str, urls: List[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for url in urls:
        print(f"  reading source: {url}")

        html = fetch_html(url)

        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        if not html:
            continue

        blocks = extract_text_blocks(html)

        for block in blocks:
            quote = normalize_quote(block)

            if not is_probably_review_text(quote):
                continue

            item = {
                "id": text_hash(company + source_name + url + quote),
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
                "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
            }

            results.append(item)

    return results


def has_configured_sources() -> bool:
    for source_config in REVIEW_SOURCE_CONFIG.values():
        if not source_config.get("enabled", False):
            continue

        direct_urls = source_config.get("direct_urls", {})

        for urls in direct_urls.values():
            if urls:
                return True

    return False


def collect_all_reviews() -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []

    for company in COMPANIES:
        print(f"Collecting employer review texts for: {company}")

        company_items: List[Dict[str, Any]] = []

        for source_name, source_config in REVIEW_SOURCE_CONFIG.items():
            if not source_config.get("enabled", False):
                continue

            urls = source_config.get("direct_urls", {}).get(company, [])

            if not urls:
                continue

            source_items = collect_from_urls(
                company=company,
                source_name=source_name,
                urls=urls,
            )

            company_items.extend(source_items)

        company_items = company_items[:MAX_QUOTES_PER_COMPANY]
        print(f"  collected valid quotes: {len(company_items)}")

        all_items.extend(company_items)

    return all_items


def merge_existing_items(existing: Dict[str, Any], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for item in existing.get("items", []):
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item

    for item in new_items:
        item_id = item.get("id")
        if item_id:
            merged[item_id] = item

    return list(merged.values())


def summarize_company(company: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    company_items = [item for item in items if item.get("company") == company]

    topic_counts: Dict[str, int] = {}
    sentiment_counts = {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    }

    for item in company_items:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        sentiment = item.get("sentiment", "neutral")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1

        if sentiment not in sentiment_counts:
            sentiment = "neutral"

        sentiment_counts[sentiment] += 1

    dominant_topics = sorted(
        topic_counts.items(),
        key=lambda pair: pair[1],
        reverse=True,
    )

    sample_quotes = company_items[:5]

    return {
        "company": company,
        "review_text_count": len(company_items),
        "dominant_topics": [
            {
                "topic": topic,
                "count": count,
            }
            for topic, count in dominant_topics[:6]
        ],
        "sentiment_counts": sentiment_counts,
        "sample_quotes": sample_quotes,
    }


def build_output(items: List[Dict[str, Any]], status: str) -> Dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "status": status,
        "source_type": "public_osint_employee_reviews",
        "method": "direct_public_url_text_extraction_keyword_topic_sentiment_v2",
        "important_note": (
            "A szöveges dolgozói értékelések publikus forrásokból származó, "
            "automatikusan tisztított minták. Az eredmény nem reprezentatív kutatás, "
            "hanem OSINT jellegű munkáltatói reputációs jelzés."
        ),
        "privacy_note": (
            "A script eltávolítja az e-mail címeket, telefonszámokat és felismerhető teljes neveket. "
            "A kimenetbe nem szabad személyes adatot menteni."
        ),
        "companies": [
            summarize_company(company, items)
            for company in COMPANIES
        ],
        "items": items,
    }


def main() -> None:
    print("Employer review text collector started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_json(OUTPUT_FILE, fallback={})

    if not has_configured_sources():
        output = build_output(items=[], status="no_sources_configured")
        save_json(OUTPUT_FILE, output)
        print("No source URLs configured.")
        print(f"Template saved: {OUTPUT_FILE}")
        return

    new_items = collect_all_reviews()
    merged_items = merge_existing_items(existing, new_items)

    status = "ok" if merged_items else "no_valid_review_texts_found"

    output = build_output(items=merged_items, status=status)
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Total stored review text items: {len(merged_items)}")


if __name__ == "__main__":
    main()
