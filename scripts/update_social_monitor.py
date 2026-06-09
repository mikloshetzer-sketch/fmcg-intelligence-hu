#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import :contentReference[oaicite:0]{index=0}hashlib
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import feedparser


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "docs" / "data"
OUT_FILE = DATA_DIR / "social-monitor.json"
STATUS_FILE = DATA_DIR / "social-monitor-status.json"

COMPANIES = [
    {
        "company": "Lidl",
        "queries": ["Lidl Hungary", "Lidl Magyarország", "Lidl akció", "Lidl panasz"],
        "mastodon_tags": ["lidl", "lidlmagyarorszag"]
    },
    {
        "company": "SPAR",
        "queries": ["SPAR Hungary", "SPAR Magyarország", "SPAR akció", "SPAR panasz"],
        "mastodon_tags": ["spar", "sparmagyarorszag"]
    },
    {
        "company": "Tesco",
        "queries": ["Tesco Hungary", "Tesco Magyarország", "Tesco akció", "Tesco panasz"],
        "mastodon_tags": ["tesco", "tescomagyarorszag"]
    },
    {
        "company": "ALDI",
        "queries": ["ALDI Hungary", "ALDI Magyarország", "ALDI akció", "ALDI panasz"],
        "mastodon_tags": ["aldi", "aldimagyarorszag"]
    },
    {
        "company": "Penny",
        "queries": ["Penny Hungary", "Penny Magyarország", "Penny akció", "Penny panasz"],
        "mastodon_tags": ["penny", "pennymagyarorszag"]
    },
    {
        "company": "Auchan",
        "queries": ["Auchan Hungary", "Auchan Magyarország", "Auchan akció", "Auchan panasz"],
        "mastodon_tags": ["auchan", "auchanmagyarorszag"]
    },
    {
        "company": "CBA",
        "queries": ["CBA Hungary", "CBA Magyarország", "CBA akció", "CBA panasz"],
        "mastodon_tags": ["cba", "cbamagyarorszag"]
    }
]


TOPIC_KEYWORDS = {
    "árak és akciók": [
        "ár", "árak", "drága", "olcsó", "akció", "kedvezmény",
        "kupon", "infláció", "price", "discount", "sale", "offer"
    ],
    "vásárlói panaszok": [
        "panasz", "rossz", "hiba", "botrány", "nem működik",
        "complaint", "problem", "issue", "bad", "scam"
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
    ]
}

POSITIVE_WORDS = [
    "jó", "kiváló", "szeretem", "kedvező", "olcsó", "gyors",
    "good", "great", "excellent", "love", "cheap", "nice"
]

NEGATIVE_WORDS = [
    "rossz", "drága", "panasz", "hiba", "botrány", "lejárt", "romlott",
    "bad", "expensive", "complaint", "problem", "issue", "scam", "poor"
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def item_id(source, title, link):
    raw = f"{source}|{title}|{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def fetch_feed(url, timeout_sleep=0.7):
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
    encoded = urllib.parse.quote(query)
    return f"https://www.reddit.com/search.rss?q={encoded}&sort=new&t=month"


def mastodon_tag_rss(tag):
    tag = tag.replace("#", "").strip()
    return f"https://mastodon.social/tags/{urllib.parse.quote(tag)}.rss"


def collect_reddit(company):
    items = []
    for query in company["queries"]:
        url = reddit_rss(query)
        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            if not title and not summary:
                continue
            items.append({
                "id": item_id("reddit", title, link),
                "source": "reddit",
                "company": company["company"],
                "title": title,
                "summary": summary[:500],
                "url": link,
                "published": getattr(entry, "published", ""),
                "query": query
            })
    return items


def collect_youtube_discovery(company):
    items = []
    for query in company["queries"]:
        yt_query = f'site:youtube.com {query} review OR panasz OR akció OR vásárlás'
        url = google_news_rss(yt_query)
        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            text = f"{title} {summary}".lower()
            if "youtube" not in text and "youtube" not in link.lower():
                continue
            items.append({
                "id": item_id("youtube", title, link),
                "source": "youtube",
                "company": company["company"],
                "title": title,
                "summary": summary[:500],
                "url": link,
                "published": getattr(entry, "published", ""),
                "query": yt_query
            })
    return items


def collect_mastodon(company):
    items = []
    for tag in company["mastodon_tags"]:
        url = mastodon_tag_rss(tag)
        for entry in fetch_feed(url):
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            items.append({
                "id": item_id("mastodon", title, link),
                "source": "mastodon",
                "company": company["company"],
                "title": title,
                "summary": summary[:500],
                "url": link,
                "published": getattr(entry, "published", ""),
                "query": f"#{tag}"
            })
    return items


def deduplicate(items):
    seen = set()
    result = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        result.append(item)
    return result


def detect_topic(items):
    scores = {topic: 0 for topic in TOPIC_KEYWORDS}
    for item in items:
        text = f'{item.get("title", "")} {item.get("summary", "")}'.lower()
        for topic, words in TOPIC_KEYWORDS.items():
            for word in words:
                if word.lower() in text:
                    scores[topic] += 1

    best_topic = max(scores, key=scores.get)
    if scores[best_topic] == 0:
        return "általános vállalati említés"
    return best_topic


def detect_sentiment(items):
    pos = 0
    neg = 0

    for item in items:
        text = f'{item.get("title", "")} {item.get("summary", "")}'.lower()
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


def calculate_social_index(total_mentions, sources_count):
    """
    Ez nem reputációs pontszám.
    Ez csak social signal intenzitás:
    - hány említés van
    - hány forrásból jön
    """
    base = min(total_mentions * 6, 80)
    diversity_bonus = min(sources_count * 7, 20)
    return min(base + diversity_bonus, 100)


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

    source_counts = {
        "reddit": sum(1 for x in all_items if x["source"] == "reddit"),
        "youtube": sum(1 for x in all_items if x["source"] == "youtube"),
        "mastodon": sum(1 for x in all_items if x["source"] == "mastodon")
    }

    active_sources = sum(1 for value in source_counts.values() if value > 0)
    mentions = len(all_items)

    return {
        "company": company["company"],
        "social_mentions": mentions,
        "social_index": calculate_social_index(mentions, active_sources),
        "social_sources": source_counts,
        "dominant_social_topic": detect_topic(all_items),
        "social_sentiment": detect_sentiment(all_items),
        "latest_items": all_items[:12],
        "method_note": "Nyílt RSS és keresési alapú social signal. Nem teljes social listening, nem reprezentatív közvélemény-kutatás.",
        "errors": errors
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    status = {
        "updated_at": now_iso(),
        "status": "ok",
        "companies": [],
        "sources": ["reddit_rss", "youtube_discovery_google_news_rss", "mastodon_tag_rss"],
        "method_note": "Első verziós Social Signal Layer. Óvatos, nyílt forrású jelzőrendszer."
    }

    for company in COMPANIES:
        result = build_company_result(company)
        results.append(result)
        status["companies"].append({
            "company": company["company"],
            "mentions": result["social_mentions"],
            "index": result["social_index"],
            "errors": result["errors"]
        })

    payload = {
        "updated_at": status["updated_at"],
        "version": "social-signal-layer-v1",
        "scope": "Hungarian FMCG retail chains",
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
