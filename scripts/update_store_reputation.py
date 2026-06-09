#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import hashlib
import urllib.parse
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"

STORE_PROFILE_FILE = DATA_DIR / "store-profiles.json"
OUT_FILE = DATA_DIR / "store-reputation.json"
STATUS_FILE = DATA_DIR / "store-reputation-status.json"
HISTORY_FILE = DATA_DIR / "store-reputation-history-2026.json"

MAX_ITEM_AGE_DAYS = 180
FETCH_SLEEP = 0.5
MAX_ITEMS_PER_STORE = 25


TOPIC_KEYWORDS = {
    "kassza és várakozás": [
        "kassza", "sor", "várakozás", "varakozas", "önkiszolgáló",
        "onkiszolgalo", "pénztár", "penztar", "queue", "checkout"
    ],
    "árak és akciók": [
        "ár", "arak", "árak", "drága", "draga", "olcsó", "olcso",
        "akció", "akcio", "kedvezmény", "kupon", "price", "discount"
    ],
    "parkoló és megközelítés": [
        "parkoló", "parkolo", "parkolás", "parkolas", "megközelítés",
        "megkozelites", "parking", "traffic", "forgalom"
    ],
    "készlet és termékelérhetőség": [
        "készlet", "keszlet", "hiány", "hiany", "elfogyott",
        "nincs", "termék", "termek", "stock", "availability"
    ],
    "dolgozói kiszolgálás": [
        "eladó", "elado", "dolgozó", "dolgozo", "személyzet",
        "szemelyzet", "udvarias", "segítőkész", "staff", "employee"
    ],
    "tisztaság és bolti élmény": [
        "tisztaság", "tisztasag", "koszos", "rendezett", "bolt",
        "üzlet", "uzlet", "élmény", "elmeny", "clean", "dirty", "store"
    ]
}


NEGATIVE_WORDS = [
    "rossz", "drága", "draga", "panasz", "hiba", "botrány", "botrany",
    "lejárt", "lejart", "romlott", "lassú", "lassu", "probléma",
    "problema", "koszos", "hiány", "hiany", "bad", "expensive",
    "complaint", "problem", "issue", "poor", "slow", "dirty"
]

POSITIVE_WORDS = [
    "jó", "jo", "kiváló", "kivalo", "olcsó", "olcso", "gyors",
    "segítőkész", "segitokesz", "udvarias", "rendezett", "tiszta",
    "good", "great", "excellent", "cheap", "fast", "clean", "helpful"
]


def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().isoformat()


def clean_text(value):
    if not value:
        return ""
    value = str(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ")
    value = value.replace("&amp;", "&")
    value = value.replace("&#32;", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize(value):
    return clean_text(value).lower()


def parse_date(value):
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)
        if dt and not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt and not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_recent(value):
    dt = parse_date(value)
    if dt is None:
        return True
    return dt >= now_utc() - timedelta(days=MAX_ITEM_AGE_DAYS)


def item_id(source, title, link):
    raw = f"{source}|{title}|{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def google_news_rss(query):
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=hu&gl=HU&ceid=HU:hu"


def fetch_feed(url):
    try:
        parsed = feedparser.parse(url)
        time.sleep(FETCH_SLEEP)
        return parsed.entries or []
    except Exception:
        return []


def load_store_profiles():
    if not STORE_PROFILE_FILE.exists():
        raise FileNotFoundError(f"Missing store profile file: {STORE_PROFILE_FILE}")

    payload = json.loads(STORE_PROFILE_FILE.read_text(encoding="utf-8"))
    return payload.get("stores", [])


def build_queries(store):
    queries = []

    for keyword in store.get("keywords", []):
        queries.extend([
            f'"{keyword}" panasz',
            f'"{keyword}" vélemény',
            f'"{keyword}" értékelés',
            f'"{keyword}" vásárlás',
            f'"{keyword}" kassza',
            f'"{keyword}" parkoló'
        ])

    return queries


def passes_store_filter(store, title, summary, link):
    text = normalize(f"{title} {summary} {link}")

    company = normalize(store.get("company", ""))
    city = normalize(store.get("city", ""))
    area = normalize(store.get("area", ""))

    if company and company not in text:
        return False

    location_hit = False

    for keyword in store.get("keywords", []):
        if normalize(keyword) in text:
            location_hit = True
            break

    if city and city in text:
        location_hit = True

    if area and area in text:
        location_hit = True

    return location_hit


def detect_topics(items):
    scores = {topic: 0 for topic in TOPIC_KEYWORDS}

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')

        for topic, words in TOPIC_KEYWORDS.items():
            for word in words:
                if word in text:
                    scores[topic] += 1

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [
        {"topic": topic, "score": score}
        for topic, score in ranked
        if score > 0
    ][:3]


def detect_sentiment(items):
    pos = 0
    neg = 0

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')

        for word in POSITIVE_WORDS:
            if word in text:
                pos += 1

        for word in NEGATIVE_WORDS:
            if word in text:
                neg += 1

    if pos == 0 and neg == 0:
        return "neutral"

    if neg > pos * 1.4:
        return "negative"

    if pos > neg * 1.4:
        return "positive"

    return "mixed"


def calculate_review_signal_index(mention_count, sentiment):
    if mention_count <= 0:
        base = 0
    elif mention_count <= 2:
        base = 15
    elif mention_count <= 5:
        base = 30
    elif mention_count <= 10:
        base = 45
    elif mention_count <= 20:
        base = 60
    else:
        base = 75

    if sentiment == "negative":
        base += 10
    elif sentiment == "mixed":
        base += 5
    elif sentiment == "positive":
        base += 3

    return min(base, 100)


def collect_store_items(store):
    items = []
    queries = build_queries(store)

    for query in queries:
        url = google_news_rss(query)

        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")

            if not title and not summary:
                continue

            if not is_recent(published):
                continue

            if not passes_store_filter(store, title, summary, link):
                continue

            item = {
                "id": item_id("google_news_rss", title, link),
                "source": "google_news_rss",
                "store_id": store["store_id"],
                "company": store["company"],
                "store_name": store["name"],
                "title": title,
                "summary": summary[:500],
                "url": link,
                "published": published,
                "query": query
            }

            items.append(item)

            if len(items) >= MAX_ITEMS_PER_STORE:
                return deduplicate(items)

    return deduplicate(items)


def deduplicate(items):
    seen = set()
    result = []

    for item in items:
        key = item.get("id")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def build_store_result(store):
    errors = []

    try:
        items = collect_store_items(store)
    except Exception as exc:
        items = []
        errors.append(str(exc))

    sentiment = detect_sentiment(items)
    topics = detect_topics(items)
    mention_count = len(items)

    return {
        "store_id": store["store_id"],
        "company": store["company"],
        "store_name": store["name"],
        "city": store.get("city", ""),
        "area": store.get("area", ""),
        "lat": store.get("lat"),
        "lon": store.get("lon"),
        "store_mentions": mention_count,
        "review_signal_index": calculate_review_signal_index(mention_count, sentiment),
        "review_sentiment": sentiment,
        "dominant_store_topic": topics[0]["topic"] if topics else "nincs elég adat",
        "top_store_topics": topics,
        "latest_items": items[:10],
        "method_note": (
            "Áruházi reputációs jelzőréteg nyílt Google News RSS keresésekből. "
            "Nem Google Reviews scraping, nem teljes vásárlói review-adatbázis."
        ),
        "errors": errors
    }


def aggregate_company_results(store_results):
    companies = {}

    for item in store_results:
        company = item["company"]

        if company not in companies:
            companies[company] = {
                "company": company,
                "stores": 0,
                "store_mentions": 0,
                "review_signal_index_sum": 0,
                "negative_stores": 0,
                "positive_stores": 0,
                "topics": {}
            }

        c = companies[company]
        c["stores"] += 1
        c["store_mentions"] += item["store_mentions"]
        c["review_signal_index_sum"] += item["review_signal_index"]

        if item["review_sentiment"] == "negative":
            c["negative_stores"] += 1

        if item["review_sentiment"] == "positive":
            c["positive_stores"] += 1

        for topic in item.get("top_store_topics", []):
            key = topic["topic"]
            c["topics"][key] = c["topics"].get(key, 0) + topic["score"]

    output = []

    for company, c in companies.items():
        avg_index = round(c["review_signal_index_sum"] / max(1, c["stores"]), 1)
        top_topics = sorted(c["topics"].items(), key=lambda x: x[1], reverse=True)

        output.append({
            "company": company,
            "stores": c["stores"],
            "store_mentions": c["store_mentions"],
            "review_signal_index": avg_index,
            "negative_stores": c["negative_stores"],
            "positive_stores": c["positive_stores"],
            "dominant_store_topic": top_topics[0][0] if top_topics else "nincs elég adat"
        })

    output.sort(key=lambda x: x["review_signal_index"], reverse=True)
    return output


def load_history():
    if not HISTORY_FILE.exists():
        return {
            "version": "store-reputation-history-v1",
            "scope": "Hungarian FMCG store-level reputation signal",
            "items": []
        }

    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": "store-reputation-history-v1",
            "scope": "Hungarian FMCG store-level reputation signal",
            "items": []
        }


def save_history(store_results, updated_at):
    history = load_history()
    date_key = updated_at[:10]

    history["items"] = [
        item for item in history.get("items", [])
        if item.get("date") != date_key
    ]

    for result in store_results:
        history["items"].append({
            "date": date_key,
            "updated_at": updated_at,
            "store_id": result["store_id"],
            "company": result["company"],
            "store_name": result["store_name"],
            "city": result["city"],
            "area": result["area"],
            "store_mentions": result["store_mentions"],
            "review_signal_index": result["review_signal_index"],
            "review_sentiment": result["review_sentiment"],
            "dominant_store_topic": result["dominant_store_topic"]
        })

    history["items"].sort(
        key=lambda x: (x.get("date", ""), x.get("company", ""), x.get("store_name", ""))
    )

    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()
    stores = load_store_profiles()

    store_results = []
    status_items = []

    for store in stores:
        result = build_store_result(store)
        store_results.append(result)

        status_items.append({
            "store_id": result["store_id"],
            "store_name": result["store_name"],
            "company": result["company"],
            "mentions": result["store_mentions"],
            "index": result["review_signal_index"],
            "sentiment": result["review_sentiment"],
            "errors": result["errors"]
        })

    company_summary = aggregate_company_results(store_results)

    payload = {
        "updated_at": updated_at,
        "version": "store-reputation-layer-v1",
        "scope": "Hungarian FMCG store-level reputation signal",
        "method_note": (
            "Áruházi reputációs jelzőréteg. "
            "Nyílt Google News RSS keresések alapján dolgozik. "
            "Nem Google Reviews scraping és nem teljes vásárlói értékelési adatbázis."
        ),
        "company_summary": company_summary,
        "stores": store_results
    }

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "store-reputation-layer-v1",
        "source": "google_news_rss",
        "store_count": len(store_results),
        "items": status_items
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    save_history(store_results, updated_at)

    print(f"Store reputation updated: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"History updated: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
