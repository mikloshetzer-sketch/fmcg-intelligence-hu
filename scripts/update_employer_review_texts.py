#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Intelligence Hungary
Employer Review Text Collector v3

Források első körben:
- Profession jellegű találatok Google News RSS-en keresztül
- Reddit publikus keresés
- LinkedIn publikus említések Google News RSS-en keresztül
- Google News RSS általános dolgozói vélemény keresések

Kimenet:
docs/data/employer-review-texts.json
"""

import json
import re
import time
import random
import hashlib
import html
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUTPUT_FILE = DATA_DIR / "employer-review-texts.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT = 25
SLEEP_MIN = 1.5
SLEEP_MAX = 4.0
MAX_ITEMS_PER_COMPANY = 25
MAX_QUOTE_LENGTH = 360


COMPANIES = {
    "Auchan": ["Auchan Magyarország", "Auchan munkahely", "Auchan dolgozói vélemény"],
    "Lidl": ["Lidl Magyarország", "Lidl munkahely", "Lidl dolgozói vélemény"],
    "Aldi": ["ALDI Magyarország", "ALDI munkahely", "ALDI dolgozói vélemény"],
    "Penny": ["PENNY Magyarország", "Penny Market munkahely", "PENNY dolgozói vélemény"],
    "Spar": ["SPAR Magyarország", "SPAR munkahely", "SPAR dolgozói vélemény"],
    "Tesco": ["Tesco Magyarország", "Tesco munkahely", "Tesco dolgozói vélemény"],
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "bérezés", "órabér", "kereset", "jövedelem",
        "pénz", "nettó", "bruttó", "alulfizetett"
    ],
    "juttatások": [
        "juttatás", "cafeteria", "bónusz", "prémium", "kedvezmény",
        "utalvány", "jutalom"
    ],
    "munkaterhelés": [
        "sok munka", "leterhelt", "túlterhelt", "hajtás", "fárasztó",
        "kevés ember", "létszámhiány", "tempó", "pörgés", "nehéz munka"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "munkaidő",
        "vasárnap", "éjszaka", "szabadnap"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "vezetőség", "felettes",
        "kommunikáció", "boltvezető", "irányítás"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "segítőkész",
        "összetartás", "jó hangulat"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "képzés", "betanítás",
        "tanulás", "lehetőség"
    ],
    "munkahelyi légkör": [
        "légkör", "stressz", "megbecsülés", "tisztelet", "hangulat",
        "konfliktus", "nyomás", "kiégés"
    ],
}


POSITIVE_WORDS = [
    "jó", "pozitív", "korrekt", "segítőkész", "stabil", "rugalmas",
    "barátságos", "megbecsül", "támogató", "fejlődés", "lehetőség",
    "kiszámítható", "elégedett", "szeretek", "ajánlom"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "leterhelt", "létszámhiány", "fárasztó", "probléma", "gyenge",
    "elégedetlen", "nyomás", "konfliktus", "kaotikus", "nem ajánlom"
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_hash(text: str) -> str:
    return hashlib.sha256(clean_text(text).lower().encode("utf-8")).hexdigest()[:16]


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

    return clean_text(text)


def normalize_quote(text: str) -> str:
    text = remove_personal_data(text)

    if len(text) > MAX_QUOTE_LENGTH:
        text = text[:MAX_QUOTE_LENGTH].rsplit(" ", 1)[0] + "..."

    return text


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(1 for kw in keywords if kw in lower)

    best_topic = max(scores, key=scores.get)

    if scores[best_topic] == 0:
        return "általános munkáltatói tapasztalat"

    return best_topic


def classify_sentiment(text: str) -> str:
    lower = text.lower()

    pos = sum(1 for word in POSITIVE_WORDS if word in lower)
    neg = sum(1 for word in NEGATIVE_WORDS if word in lower)

    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def is_relevant_review_text(text: str, company: str) -> bool:
    text = clean_text(text)
    lower = text.lower()

    if len(text) < 45:
        return False

    if len(text.split()) < 7:
        return False

    company_terms = [company.lower()]
    if company == "Aldi":
        company_terms.append("aldi")
    if company == "Spar":
        company_terms.append("spar")
    if company == "Penny":
        company_terms.append("penny")

    if not any(term in lower for term in company_terms):
        return False

    review_terms = [
        "dolgozó", "munkavállaló", "munkahely", "munka", "munkatárs",
        "kolléga", "fizetés", "bér", "beosztás", "műszak", "vezető",
        "tapasztalat", "vélemény", "értékelés", "állás", "karrier"
    ]

    if not any(term in lower for term in review_terms):
        return False

    blocked = [
        "cookie", "javascript", "adatvédelmi", "bejelentkezés",
        "regisztráció", "elfogadom", "newsletter", "hirdetés"
    ]

    if any(term in lower for term in blocked):
        return False

    return True


def request_url(url: str) -> Optional[str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            print(f"  skipped status={response.status_code}: {url}")
            return None
        return response.text
    except Exception as error:
        print(f"  request failed: {url} | {error}")
        return None


def google_news_rss_search(query: str) -> List[Dict[str, str]]:
    encoded = quote_plus(query)
    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}&hl=hu&gl=HU&ceid=HU:hu"
    )

    xml_text = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not xml_text:
        return []

    results = []

    try:
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title", default=""))
            link = clean_text(item.findtext("link", default=""))
            description = clean_text(item.findtext("description", default=""))
            pub_date = clean_text(item.findtext("pubDate", default=""))

            if title or description:
                results.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                })
    except Exception as error:
        print(f"  RSS parse failed for query={query}: {error}")

    return results


def reddit_public_search(query: str) -> List[Dict[str, str]]:
    encoded = quote_plus(query)
    url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit=15"

    raw = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not raw:
        return []

    results = []

    try:
        data = json.loads(raw)
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})
            title = clean_text(post.get("title", ""))
            selftext = clean_text(post.get("selftext", ""))
            permalink = post.get("permalink", "")
            url_full = f"https://www.reddit.com{permalink}" if permalink else ""

            combined = clean_text(f"{title}. {selftext}")

            results.append({
                "title": title,
                "link": url_full,
                "description": combined,
                "pub_date": str(post.get("created_utc", "")),
            })

    except Exception as error:
        print(f"  Reddit parse failed for query={query}: {error}")

    return results


def build_item(
    company: str,
    source: str,
    source_url: str,
    raw_text: str,
    pub_date: str = "",
) -> Optional[Dict[str, Any]]:
    quote = normalize_quote(raw_text)

    if not is_relevant_review_text(quote, company):
        return None

    item_id = make_hash(company + source + source_url + quote)

    return {
        "id": item_id,
        "company": company,
        "source": source,
        "source_url": source_url,
        "published_or_found_date": pub_date,
        "date_collected": now_iso(),
        "role": None,
        "topic": classify_topic(quote),
        "sentiment": classify_sentiment(quote),
        "quote": quote,
        "length": len(quote),
        "confidence": "medium",
        "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
    }


def collect_google_news_items(company: str, aliases: List[str]) -> List[Dict[str, Any]]:
    queries = []

    for alias in aliases:
        queries.extend([
            f'"{alias}" dolgozói vélemény',
            f'"{alias}" munkavállalói vélemény',
            f'"{alias}" munkahely értékelés',
            f'"{alias}" fizetés beosztás vezető',
            f'"{alias}" site:profession.hu',
            f'"{alias}" site:linkedin.com',
        ])

    items = []

    for query in queries:
        print(f"  Google News RSS query: {query}")
        results = google_news_rss_search(query)

        for result in results:
            raw_text = clean_text(
                f"{result.get('title', '')}. {result.get('description', '')}"
            )

            source = "google_news_rss"

            link = result.get("link", "")

            if "profession.hu" in link.lower() or "profession.hu" in raw_text.lower():
                source = "profession_via_google_news"
            elif "linkedin.com" in link.lower() or "linkedin.com" in raw_text.lower():
                source = "linkedin_via_google_news"

            item = build_item(
                company=company,
                source=source,
                source_url=link,
                raw_text=raw_text,
                pub_date=result.get("pub_date", ""),
            )

            if item:
                items.append(item)

    return items


def collect_reddit_items(company: str, aliases: List[str]) -> List[Dict[str, Any]]:
    queries = []

    for alias in aliases:
        queries.extend([
            f'"{alias}" munka',
            f'"{alias}" fizetés',
            f'"{alias}" dolgozó',
            f'"{alias}" vélemény',
        ])

    items = []

    for query in queries:
        print(f"  Reddit query: {query}")
        results = reddit_public_search(query)

        for result in results:
            raw_text = clean_text(
                f"{result.get('title', '')}. {result.get('description', '')}"
            )

            item = build_item(
                company=company,
                source="reddit_public_search",
                source_url=result.get("link", ""),
                raw_text=raw_text,
                pub_date=result.get("pub_date", ""),
            )

            if item:
                items.append(item)

    return items


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


def deduplicate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for item in items:
        item_id = item.get("id")
        quote = item.get("quote", "")
        quote_hash = make_hash(quote)

        key = item_id or quote_hash

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def merge_existing(existing: Dict[str, Any], new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = {}

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

    source_counts: Dict[str, int] = {}

    for item in company_items:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        sentiment = item.get("sentiment", "neutral")
        source = item.get("source", "unknown")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        if sentiment not in sentiment_counts:
            sentiment = "neutral"

        sentiment_counts[sentiment] += 1

    dominant_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    dominant_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "company": company,
        "review_text_count": len(company_items),
        "dominant_topics": [
            {"topic": topic, "count": count}
            for topic, count in dominant_topics[:6]
        ],
        "sentiment_counts": sentiment_counts,
        "source_counts": [
            {"source": source, "count": count}
            for source, count in dominant_sources
        ],
        "sample_quotes": company_items[:5],
    }


def build_output(items: List[Dict[str, Any]], status: str) -> Dict[str, Any]:
    return {
        "updated_at": now_iso(),
        "status": status,
        "source_type": "public_osint_employee_reviews",
        "method": "profession_reddit_linkedin_google_news_osint_v3",
        "important_note": (
            "Az adatok publikus OSINT forrásokból származó szöveges minták. "
            "A gyűjtés nem reprezentatív dolgozói felmérés, hanem munkáltatói reputációs jelzés. "
            "A LinkedIn és Profession esetében az első kör Google News/RSS találatokra és publikus "
            "említésekre támaszkodik, nem belépéshez kötött tartalomra."
        ),
        "privacy_note": (
            "A script automatikusan eltávolítja az e-mail címeket, telefonszámokat "
            "és felismerhető teljes neveket. Személyes adatot nem szabad menteni."
        ),
        "companies": [
            summarize_company(company, items)
            for company in COMPANIES.keys()
        ],
        "items": items,
    }


def collect_all() -> List[Dict[str, Any]]:
    all_items = []

    for company, aliases in COMPANIES.items():
        print(f"Collecting employee voice data for: {company}")

        company_items = []

        google_items = collect_google_news_items(company, aliases)
        reddit_items = collect_reddit_items(company, aliases)

        company_items.extend(google_items)
        company_items.extend(reddit_items)

        company_items = deduplicate_items(company_items)
        company_items = company_items[:MAX_ITEMS_PER_COMPANY]

        print(f"  valid stored items for {company}: {len(company_items)}")

        all_items.extend(company_items)

    return deduplicate_items(all_items)


def main() -> None:
    print("Employer review OSINT collector started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_json(OUTPUT_FILE, fallback={})
    new_items = collect_all()

    merged_items = merge_existing(existing, new_items)
    merged_items = deduplicate_items(merged_items)

    status = "ok" if merged_items else "no_valid_review_texts_found"

    output = build_output(merged_items, status)
    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Total stored items: {len(merged_items)}")
    print(f"Status: {status}")


if __name__ == "__main__":
    main()
