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

OUT_FILE = DATA_DIR / "social-monitor.json"
STATUS_FILE = DATA_DIR / "social-monitor-status.json"
HISTORY_FILE = DATA_DIR / "social-history-2026.json"

MAX_ITEM_AGE_DAYS = 180
MAX_ITEMS_PER_SOURCE_PER_COMPANY = 40
FETCH_SLEEP = 0.6


HU_RELEVANCE_TERMS = [
    "magyarország",
    "magyarorszag",
    "hungary",
    "hungarian",
    "budapest",
    "budaörs",
    "budaors",
    "monor",
    "forint",
    "huf",
    "ft",
    "akciós újság",
    "akcios ujsag",
    "lidl magyarország",
    "spar magyarország",
    "tesco magyarország",
    "aldi magyarország",
    "auchan magyarország",
    "penny magyarország",
    "penny market magyarország",
    "cba príma",
    "cba prima"
]


COMPANIES = [
    {
        "company": "Lidl",
        "queries": [
            "Lidl Magyarország",
            "Lidl Hungary",
            "Lidl akció",
            "Lidl panasz",
            "Lidl Scan Go"
        ],
        "required_terms": ["lidl"],
        "mastodon_tags": ["lidl", "lidlmagyarorszag"]
    },
    {
        "company": "SPAR",
        "queries": [
            "SPAR Magyarország",
            "SPAR Hungary",
            "Interspar Magyarország",
            "SPAR akció",
            "SPAR panasz"
        ],
        "required_terms": ["spar", "interspar"],
        "mastodon_tags": ["spar", "sparmagyarorszag", "interspar"]
    },
    {
        "company": "Tesco",
        "queries": [
            "Tesco Magyarország",
            "Tesco Hungary",
            "Tesco akció",
            "Tesco panasz",
            "Tesco online bevásárlás"
        ],
        "required_terms": ["tesco"],
        "mastodon_tags": ["tesco", "tescomagyarorszag"]
    },
    {
        "company": "ALDI",
        "queries": [
            "ALDI Magyarország",
            "ALDI Hungary",
            "Aldi akció",
            "Aldi panasz"
        ],
        "required_terms": ["aldi"],
        "mastodon_tags": ["aldi", "aldimagyarorszag"]
    },
    {
        "company": "Penny",
        "queries": [
            "Penny Market Magyarország",
            "Penny Market Hungary",
            "Penny Market akció",
            "Penny Market panasz"
        ],
        "required_terms": ["penny market", "penny"],
        "context_terms": [
            "market", "magyarország", "magyarorszag", "hungary", "áruház",
            "aruhaz", "bolt", "üzlet", "uzlet", "akció", "akcio",
            "panasz", "bevásárlás", "bevasarlas", "supermarket",
            "retail", "élelmiszer", "elelmiszer"
        ],
        "mastodon_tags": ["pennymarket", "pennymagyarorszag"]
    },
    {
        "company": "Auchan",
        "queries": [
            "Auchan Magyarország",
            "Auchan Hungary",
            "Auchan akció",
            "Auchan panasz",
            "Auchan online"
        ],
        "required_terms": ["auchan"],
        "mastodon_tags": ["auchan", "auchanmagyarorszag"]
    },
    {
        "company": "CBA",
        "queries": [
            "CBA Magyarország",
            "CBA üzlet",
            "CBA akció",
            "CBA panasz",
            "CBA Príma"
        ],
        "required_terms": ["cba", "príma", "prima"],
        "context_terms": [
            "élelmiszer", "elelmiszer", "bolt", "üzlet", "uzlet",
            "áruház", "aruhaz", "akció", "akcio", "panasz",
            "bevásárlás", "bevasarlas", "retail", "supermarket"
        ],
        "mastodon_tags": ["cba", "cbaprima"]
    }
]


TOPIC_KEYWORDS = {
    "árak és akciók": [
        "ár", "árak", "drága", "olcsó", "akció", "akcio", "kedvezmény",
        "kupon", "infláció", "price", "discount", "sale", "offer"
    ],
    "vásárlói panaszok": [
        "panasz", "rossz", "hiba", "botrány", "nem működik",
        "complaint", "problem", "issue", "bad", "scam", "kritika"
    ],
    "bolti élmény": [
        "bolt", "üzlet", "uzlet", "sor", "kassza", "parkoló", "parkolo",
        "eladó", "elado", "store", "shop", "queue", "cashier", "experience"
    ],
    "munkaerő és foglalkoztatás": [
        "munka", "állás", "allas", "dolgozó", "dolgozo", "fizetés",
        "ber", "bér", "munkavállaló", "job", "salary", "employee",
        "worker", "staff", "vacature"
    ],
    "termék és minőség": [
        "termék", "termek", "minőség", "minoseg", "friss", "lejárt",
        "lejart", "romlott", "élelmiszer", "product", "quality",
        "fresh", "expired", "food", "recall", "visszahívás"
    ],
    "digitalizáció és önkiszolgálás": [
        "scan", "scan&go", "scan go", "önkiszolgáló", "onkiszolgalo",
        "app", "alkalmazás", "online", "mobil", "self-checkout",
        "self checkout", "wifi", "wi-fi"
    ],
    "ellátási lánc és logisztika": [
        "logisztika", "szállítás", "szallitas", "ellátási lánc",
        "supply chain", "shipping", "container", "reederei",
        "teherautó", "truck", "diesel", "elektromos"
    ]
}


POSITIVE_WORDS = [
    "jó", "jo", "kiváló", "kivalo", "szeretem", "kedvező", "kedvezo",
    "olcsó", "olcso", "gyors", "hasznos", "elégedett",
    "good", "great", "excellent", "love", "cheap", "nice", "useful"
]

NEGATIVE_WORDS = [
    "rossz", "drága", "draga", "panasz", "hiba", "botrány",
    "botrany", "lejárt", "lejart", "romlott", "lassú", "lassu",
    "probléma", "problema", "bad", "expensive", "complaint",
    "problem", "issue", "scam", "poor", "slow", "warning",
    "recall", "outage", "closed"
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


def item_id(source, title, link):
    raw = f"{source}|{title}|{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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


def is_recent(published_value, max_age_days=MAX_ITEM_AGE_DAYS):
    dt = parse_date(published_value)

    if dt is None:
        return True

    return dt >= now_utc() - timedelta(days=max_age_days)


def fetch_feed(url, timeout_sleep=FETCH_SLEEP):
    try:
        parsed = feedparser.parse(url)
        time.sleep(timeout_sleep)
        return parsed.entries or []
    except Exception:
        return []


def google_news_rss(query):
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=hu&gl=HU&ceid=HU:hu"


def reddit_rss(query):
    encoded = urllib.parse.quote(f'"{query}"')
    return f"https://www.reddit.com/search.rss?q={encoded}&sort=new&t=month"


def mastodon_tag_rss(tag):
    tag = tag.replace("#", "").strip()
    return f"https://mastodon.social/tags/{urllib.parse.quote(tag)}.rss"


def detect_hu_relevance(title, summary, link, query):
    text = normalize(f"{title} {summary} {link} {query}")

    if any(term.lower() in text for term in HU_RELEVANCE_TERMS):
        return 1.0

    if ".hu" in text or "/hu/" in text:
        return 0.8

    return 0.25


def passes_company_filter(company, title, summary, link):
    text = normalize(f"{title} {summary} {link}")

    required_terms = company.get("required_terms", [])
    has_company = any(term.lower() in text for term in required_terms)

    if not has_company:
        return False

    context_terms = company.get("context_terms", [])
    if context_terms:
        return any(term.lower() in text for term in context_terms)

    return True


def make_item(source, company, title, summary, link, published, query):
    relevance = detect_hu_relevance(title, summary, link, query)

    return {
        "id": item_id(source, title, link),
        "source": source,
        "company": company["company"],
        "title": clean_text(title),
        "summary": clean_text(summary)[:500],
        "url": link,
        "published": published or "",
        "query": query,
        "hu_relevance": relevance
    }


def collect_reddit(company):
    items = []

    for query in company["queries"]:
        url = reddit_rss(query)

        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")

            if not title and not summary:
                continue

            if not is_recent(published):
                continue

            if not passes_company_filter(company, title, summary, link):
                continue

            items.append(make_item("reddit", company, title, summary, link, published, query))

            if len(items) >= MAX_ITEMS_PER_SOURCE_PER_COMPANY:
                return items

    return items


def collect_youtube_discovery(company):
    items = []

    for query in company["queries"]:
        yt_query = (
            f'site:youtube.com "{query}" '
            f'(review OR panasz OR akció OR vásárlás OR bolt OR üzlet)'
        )

        url = google_news_rss(yt_query)

        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")

            text = normalize(f"{title} {summary} {link}")

            if "youtube" not in text:
                continue

            if not is_recent(published):
                continue

            if not passes_company_filter(company, title, summary, link):
                continue

            items.append(make_item("youtube", company, title, summary, link, published, yt_query))

            if len(items) >= MAX_ITEMS_PER_SOURCE_PER_COMPANY:
                return items

    return items


def collect_mastodon(company):
    items = []

    for tag in company["mastodon_tags"]:
        url = mastodon_tag_rss(tag)

        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")

            if not title and not summary:
                continue

            if not is_recent(published):
                continue

            if not passes_company_filter(company, title, summary, link):
                continue

            items.append(make_item("mastodon", company, title, summary, link, published, f"#{tag}"))

            if len(items) >= MAX_ITEMS_PER_SOURCE_PER_COMPANY:
                return items

    return items


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


def score_topics(items):
    scores = {topic: 0.0 for topic in TOPIC_KEYWORDS}

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')
        relevance = float(item.get("hu_relevance", 0.25))

        for topic, words in TOPIC_KEYWORDS.items():
            for word in words:
                if word.lower() in text:
                    scores[topic] += relevance

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_topics = [
        {
            "topic": topic,
            "score": round(score, 2)
        }
        for topic, score in ranked
        if score > 0
    ]

    return top_topics[:3]


def detect_topic(items):
    top_topics = score_topics(items)

    if not top_topics:
        return "általános vállalati említés"

    return top_topics[0]["topic"]


def detect_sentiment(items):
    pos = 0.0
    neg = 0.0

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')
        relevance = float(item.get("hu_relevance", 0.25))

        for word in POSITIVE_WORDS:
            if word in text:
                pos += relevance

        for word in NEGATIVE_WORDS:
            if word in text:
                neg += relevance

    if pos == 0 and neg == 0:
        return "neutral"

    if neg > pos * 1.4:
        return "negative"

    if pos > neg * 1.4:
        return "positive"

    return "mixed"


def calculate_weighted_mentions(items):
    return round(sum(float(item.get("hu_relevance", 0.25)) for item in items), 2)


def calculate_social_index(weighted_mentions, sources_count, sentiment):
    if weighted_mentions <= 0:
        base = 0
    elif weighted_mentions <= 3:
        base = 12
    elif weighted_mentions <= 8:
        base = 25
    elif weighted_mentions <= 15:
        base = 40
    elif weighted_mentions <= 30:
        base = 55
    elif weighted_mentions <= 50:
        base = 70
    elif weighted_mentions <= 80:
        base = 82
    else:
        base = 90

    diversity_bonus = min(sources_count * 4, 12)

    sentiment_bonus = 0
    if sentiment == "negative":
        sentiment_bonus = 5
    elif sentiment == "mixed":
        sentiment_bonus = 3

    return min(base + diversity_bonus + sentiment_bonus, 100)


def build_company_result(company):
    all_items = []
    errors = []

    try:
        all_items.extend(collect_reddit(company))
    except Exception as exc:
        errors.append(f"reddit: {exc}")

    try:
        all_items.extend(collect_youtube_discovery(company))
    except Exception as exc:
        errors.append(f"youtube: {exc}")

    try:
        all_items.extend(collect_mastodon(company))
    except Exception as exc:
        errors.append(f"mastodon: {exc}")

    all_items = deduplicate(all_items)

    all_items.sort(
        key=lambda x: parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True
    )

    source_counts = {
        "reddit": sum(1 for x in all_items if x.get("source") == "reddit"),
        "youtube": sum(1 for x in all_items if x.get("source") == "youtube"),
        "mastodon": sum(1 for x in all_items if x.get("source") == "mastodon")
    }

    active_sources = sum(1 for value in source_counts.values() if value > 0)
    mentions = len(all_items)
    weighted_mentions = calculate_weighted_mentions(all_items)
    hu_mentions = sum(1 for item in all_items if float(item.get("hu_relevance", 0.25)) >= 0.8)

    sentiment = detect_sentiment(all_items)
    top_topics = score_topics(all_items)

    return {
        "company": company["company"],
        "social_mentions": mentions,
        "weighted_social_mentions": weighted_mentions,
        "hu_relevant_mentions": hu_mentions,
        "social_index": calculate_social_index(weighted_mentions, active_sources, sentiment),
        "social_sources": source_counts,
        "dominant_social_topic": detect_topic(all_items),
        "top_social_topics": top_topics,
        "social_sentiment": sentiment,
        "latest_items": all_items[:12],
        "method_note": (
            "Nyílt RSS és keresési alapú social signal. "
            "Nem teljes social listening, nem reprezentatív közvélemény-kutatás. "
            "A V1.3 verzió magyar relevancia súlyozást és történeti mentést használ."
        ),
        "errors": errors
    }


def load_history():
    if not HISTORY_FILE.exists():
        return {
            "version": "social-history-v1",
            "scope": "Hungarian FMCG retail chains",
            "items": []
        }

    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": "social-history-v1",
            "scope": "Hungarian FMCG retail chains",
            "items": []
        }


def save_history(results, updated_at):
    history = load_history()
    date_key = updated_at[:10]

    history["items"] = [
        item for item in history.get("items", [])
        if item.get("date") != date_key
    ]

    for result in results:
        history["items"].append({
            "date": date_key,
            "updated_at": updated_at,
            "company": result["company"],
            "social_mentions": result["social_mentions"],
            "weighted_social_mentions": result["weighted_social_mentions"],
            "hu_relevant_mentions": result["hu_relevant_mentions"],
            "social_index": result["social_index"],
            "social_sentiment": result["social_sentiment"],
            "dominant_social_topic": result["dominant_social_topic"],
            "social_sources": result["social_sources"]
        })

    history["items"].sort(
        key=lambda x: (x.get("date", ""), x.get("company", ""))
    )

    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    updated_at = now_iso()

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "social-signal-layer-v1.3",
        "companies": [],
        "sources": [
            "reddit_rss",
            "youtube_discovery_google_news_rss",
            "mastodon_tag_rss"
        ],
        "filters": {
            "max_item_age_days": MAX_ITEM_AGE_DAYS,
            "max_items_per_source_per_company": MAX_ITEMS_PER_SOURCE_PER_COMPANY,
            "company_context_filter": True,
            "hungarian_relevance_weighting": True
        },
        "method_note": (
            "Social Signal Layer V1.3. "
            "Óvatos, nyílt forrású jelzőrendszer frissességi, relevancia- és magyar piaci súlyozással."
        )
    }

    for company in COMPANIES:
        result = build_company_result(company)
        results.append(result)

        status["companies"].append({
            "company": company["company"],
            "mentions": result["social_mentions"],
            "weighted_mentions": result["weighted_social_mentions"],
            "hu_relevant_mentions": result["hu_relevant_mentions"],
            "index": result["social_index"],
            "sources": result["social_sources"],
            "sentiment": result["social_sentiment"],
            "topic": result["dominant_social_topic"],
            "errors": result["errors"]
        })

    payload = {
        "updated_at": updated_at,
        "version": "social-signal-layer-v1.3",
        "scope": "Hungarian FMCG retail chains",
        "method_note": (
            "Ez social signal réteg, nem teljes social analytics. "
            "A mutató friss, nyílt forrású említésekből készül, magyar piaci relevancia súlyozással."
        ),
        "items": results
    }

    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    save_history(results, updated_at)

    print(f"Social monitor updated: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")
    print(f"History updated: {HISTORY_FILE}")


if __name__ == "__main__":
    main()
