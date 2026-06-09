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


MAX_ITEM_AGE_DAYS = 180
MAX_ITEMS_PER_SOURCE_PER_COMPANY = 40
FETCH_SLEEP = 0.6


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
            "market", "magyarország", "hungary", "áruház", "bolt",
            "üzlet", "akció", "panasz", "bevásárlás", "supermarket",
            "retail", "élelmiszer"
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
            "élelmiszer", "bolt", "üzlet", "áruház", "akció",
            "panasz", "bevásárlás", "retail", "supermarket"
        ],
        "mastodon_tags": ["cba", "cbaprima"]
    }
]


TOPIC_KEYWORDS = {
    "árak és akciók": [
        "ár", "árak", "drága", "olcsó", "akció", "kedvezmény",
        "kupon", "infláció", "price", "discount", "sale", "offer"
    ],
    "vásárlói panaszok": [
        "panasz", "rossz", "hiba", "botrány", "nem működik",
        "complaint", "problem", "issue", "bad", "scam", "kritika"
    ],
    "bolti élmény": [
        "bolt", "üzlet", "sor", "kassza", "parkoló", "eladó",
        "store", "shop", "queue", "cashier", "experience"
    ],
    "munkaerő és foglalkoztatás": [
        "munka", "állás", "dolgozó", "fizetés", "bér", "munkavállaló",
        "job", "salary", "employee", "worker", "staff"
    ],
    "termék és minőség": [
        "termék", "minőség", "friss", "lejárt", "romlott", "élelmiszer",
        "product", "quality", "fresh", "expired", "food"
    ],
    "digitalizáció és önkiszolgálás": [
        "scan", "scan&go", "scan go", "önkiszolgáló", "app", "alkalmazás",
        "online", "mobil", "self-checkout", "self checkout"
    ]
}


POSITIVE_WORDS = [
    "jó", "kiváló", "szeretem", "kedvező", "olcsó", "gyors",
    "hasznos", "elégedett", "good", "great", "excellent",
    "love", "cheap", "nice", "useful"
]

NEGATIVE_WORDS = [
    "rossz", "drága", "panasz", "hiba", "botrány", "lejárt", "romlott",
    "lassú", "probléma", "bad", "expensive", "complaint", "problem",
    "issue", "scam", "poor", "slow"
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
    return {
        "id": item_id(source, title, link),
        "source": source,
        "company": company["company"],
        "title": clean_text(title),
        "summary": clean_text(summary)[:500],
        "url": link,
        "published": published or "",
        "query": query
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

            items.append(
                make_item("reddit", company, title, summary, link, published, query)
            )

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

            items.append(
                make_item("youtube", company, title, summary, link, published, yt_query)
            )

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

            items.append(
                make_item("mastodon", company, title, summary, link, published, f"#{tag}")
            )

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
    scores = {topic: 0 for topic in TOPIC_KEYWORDS}

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')

        for topic, words in TOPIC_KEYWORDS.items():
            for word in words:
                if word.lower() in text:
                    scores[topic] += 1

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    top_topics = [
        {"topic": topic, "score": score}
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


def calculate_social_index(total_mentions, sources_count, sentiment):
    """
    Social Signal Index V1.2

    Ez nem reputációs pontszám.
    Ez óvatos intenzitási jelző:
    - friss említések száma
    - aktív források száma
    - negatív aktivitás enyhe kockázati felára
    """

    if total_mentions <= 0:
        base = 0
    elif total_mentions <= 5:
        base = 15
    elif total_mentions <= 15:
        base = 30
    elif total_mentions <= 30:
        base = 45
    elif total_mentions <= 60:
        base = 60
    elif total_mentions <= 100:
        base = 75
    else:
        base = 85

    diversity_bonus = min(sources_count * 5, 15)

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
    sentiment = detect_sentiment(all_items)
    top_topics = score_topics(all_items)

    return {
        "company": company["company"],
        "social_mentions": mentions,
        "social_index": calculate_social_index(mentions, active_sources, sentiment),
        "social_sources": source_counts,
        "dominant_social_topic": detect_topic(all_items),
        "top_social_topics": top_topics,
        "social_sentiment": sentiment,
        "latest_items": all_items[:12],
        "method_note": (
            "Nyílt RSS és keresési alapú social signal. "
            "Nem teljes social listening, nem reprezentatív közvélemény-kutatás. "
            "A V1.2 verzió 180 napos frissességi szűrést és cégnév-kontekstus szűrést használ."
        ),
        "errors": errors
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    status = {
        "updated_at": now_iso(),
        "status": "ok",
        "version": "social-signal-layer-v1.2",
        "companies": [],
        "sources": [
            "reddit_rss",
            "youtube_discovery_google_news_rss",
            "mastodon_tag_rss"
        ],
        "filters": {
            "max_item_age_days": MAX_ITEM_AGE_DAYS,
            "max_items_per_source_per_company": MAX_ITEMS_PER_SOURCE_PER_COMPANY,
            "company_context_filter": True
        },
        "method_note": (
            "Social Signal Layer V1.2. "
            "Óvatos, nyílt forrású jelzőrendszer frissességi és relevanciaszűréssel."
        )
    }

    for company in COMPANIES:
        result = build_company_result(company)
        results.append(result)

        status["companies"].append({
            "company": company["company"],
            "mentions": result["social_mentions"],
            "index": result["social_index"],
            "sources": result["social_sources"],
            "sentiment": result["social_sentiment"],
            "topic": result["dominant_social_topic"],
            "errors": result["errors"]
        })

    payload = {
        "updated_at": status["updated_at"],
        "version": "social-signal-layer-v1.2",
        "scope": "Hungarian FMCG retail chains",
        "method_note": (
            "Ez social signal réteg, nem teljes social analytics. "
            "A mutató friss, nyílt forrású említésekből készül."
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

    print(f"Social monitor updated: {OUT_FILE}")
    print(f"Status written: {STATUS_FILE}")


if __name__ == "__main__":
    main()
