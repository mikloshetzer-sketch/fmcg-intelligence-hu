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

PROFILE_FILE = DATA_DIR / "company-profiles.json"
OUT_FILE = DATA_DIR / "social-monitor.json"
STATUS_FILE = DATA_DIR / "social-monitor-status.json"
HISTORY_FILE = DATA_DIR / "social-history-2026.json"

MAX_ITEM_AGE_DAYS = 180
MAX_ITEMS_PER_SOURCE_PER_COMPANY = 40
FETCH_SLEEP = 0.6

DASHBOARD_RELEVANCE_THRESHOLD = 0.8
BACKGROUND_RELEVANCE_THRESHOLD = 0.5


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
    ".hu",
    "/hu/",
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
    "cba prima",
    "magyar boltok",
    "magyarországi"
]


FOREIGN_NOISE_TERMS = [
    "denmark",
    "danmark",
    "france",
    "germany",
    "deutschland",
    "netherlands",
    "holland",
    "belgium",
    "ireland",
    "dublin",
    "uk",
    "united kingdom",
    "london",
    "scotland",
    "wales",
    "austria",
    "österreich",
    "italy",
    "spain",
    "portugal",
    "sweden",
    "finland",
    "norway",
    "lanaken",
    "maastricht",
    "clubcard jumper",
    "charity shop",
    "cineworld",
    "virgin red",
    "mandalorian"
]


TOPIC_KEYWORDS = {
    "árak és akciók": [
        "ár", "árak", "arak", "drága", "draga", "olcsó", "olcso",
        "akció", "akcio", "kedvezmény", "kedvezmeny", "kupon",
        "infláció", "inflacio", "price", "discount", "sale", "offer",
        "clubcard", "lidl plus", "hűségakció", "husegakcio"
    ],
    "vásárlói panaszok": [
        "panasz", "rossz", "hiba", "botrány", "botrany",
        "nem működik", "nem mukodik", "complaint", "problem",
        "issue", "bad", "scam", "kritika", "túlterheltek",
        "tulterheltek", "nem enged", "leállás", "leallas"
    ],
    "bolti élmény": [
        "bolt", "üzlet", "uzlet", "sor", "kassza", "parkoló",
        "parkolo", "eladó", "elado", "store", "shop", "queue",
        "cashier", "experience", "vásárlás", "bevasarlas"
    ],
    "munkaerő és foglalkoztatás": [
        "munka", "állás", "allas", "dolgozó", "dolgozo",
        "fizetés", "fizetes", "bér", "ber", "munkavállaló",
        "munkavallalo", "job", "salary", "employee", "worker",
        "staff", "vacature"
    ],
    "termék és minőség": [
        "termék", "termek", "minőség", "minoseg", "friss",
        "lejárt", "lejart", "romlott", "élelmiszer", "elelmiszer",
        "product", "quality", "fresh", "expired", "food", "recall",
        "visszahívás", "visszahivas"
    ],
    "digitalizáció és önkiszolgálás": [
        "scan", "scan&go", "scan go", "önkiszolgáló", "onkiszolgalo",
        "app", "alkalmazás", "alkalmazas", "online", "mobil",
        "self-checkout", "self checkout", "wifi", "wi-fi", "qr"
    ],
    "ellátási lánc és logisztika": [
        "logisztika", "szállítás", "szallitas", "ellátási lánc",
        "ellatasi lanc", "supply chain", "shipping", "container",
        "reederei", "teherautó", "teherauto", "truck", "diesel",
        "elektromos"
    ]
}


POSITIVE_WORDS = [
    "jó", "jo", "kiváló", "kivalo", "szeretem", "kedvező",
    "kedvezo", "olcsó", "olcso", "gyors", "hasznos",
    "elégedett", "elegedett", "megéri", "megeri", "spórol",
    "sporol", "good", "great", "excellent", "love", "cheap",
    "nice", "useful", "helpful", "fast", "saving", "saves"
]


NEGATIVE_WORDS = [
    "rossz", "drága", "draga", "panasz", "hiba", "botrány",
    "botrany", "lejárt", "lejart", "romlott", "lassú", "lassu",
    "probléma", "problema", "túlterhelt", "tulterhelt",
    "nem működik", "nem mukodik", "nem enged", "eltűnik",
    "eltunik", "hiány", "hiany", "bad", "expensive", "complaint",
    "problem", "issue", "scam", "poor", "slow", "warning",
    "recall", "outage", "closed", "insane", "trouble"
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


def load_company_profiles():
    if not PROFILE_FILE.exists():
        raise FileNotFoundError(f"Missing company profile file: {PROFILE_FILE}")

    profiles = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))

    companies = []
    for name, profile in profiles.items():
        companies.append({
            "company": name,
            "queries": profile.get("keywords", []),
            "required_terms": profile.get("required_terms", []),
            "context_terms": profile.get("context_terms", []),
            "mastodon_tags": profile.get("social_tags", []),
            "website": profile.get("website", ""),
            "country": profile.get("country", "Hungary")
        })

    return companies


def detect_hu_relevance(title, summary, link, query):
    text = normalize(f"{title} {summary} {link} {query}")

    if any(term.lower() in text for term in HU_RELEVANCE_TERMS):
        return 1.0

    if ".hu" in text or "/hu/" in text:
        return 0.8

    if any(term.lower() in text for term in FOREIGN_NOISE_TERMS):
        return 0.25

    return 0.5


def relevance_bucket(value):
    value = float(value)

    if value >= DASHBOARD_RELEVANCE_THRESHOLD:
        return "dashboard"

    if value >= BACKGROUND_RELEVANCE_THRESHOLD:
        return "background"

    return "discarded"


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
        "hu_relevance": relevance,
        "relevance_bucket": relevance_bucket(relevance)
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


def classify_item_sentiment(item):
    text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')

    pos = 0
    neg = 0

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

    return [
        {
            "topic": topic,
            "score": round(score, 2)
        }
        for topic, score in ranked
        if score > 0
    ][:5]


def detect_topic(items):
    top_topics = score_topics(items)
    if not top_topics:
        return "általános vállalati említés"
    return top_topics[0]["topic"]


def detect_sentiment(items):
    pos = 0.0
    neg = 0.0

    for item in items:
        sentiment = item.get("item_sentiment") or classify_item_sentiment(item)
        relevance = float(item.get("hu_relevance", 0.25))

        if sentiment == "positive":
            pos += relevance
        elif sentiment == "negative":
            neg += relevance
        elif sentiment == "mixed":
            pos += relevance * 0.5
            neg += relevance * 0.5

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


def build_topic_sentiment(items):
    topic_sentiment = {}

    for item in items:
        text = normalize(f'{item.get("title", "")} {item.get("summary", "")}')
        relevance = float(item.get("hu_relevance", 0.25))
        sentiment = item.get("item_sentiment") or classify_item_sentiment(item)

        for topic, words in TOPIC_KEYWORDS.items():
            if any(word.lower() in text for word in words):
                if topic not in topic_sentiment:
                    topic_sentiment[topic] = {
                        "positive": 0.0,
                        "neutral": 0.0,
                        "negative": 0.0,
                        "mixed": 0.0,
                        "dominant": "neutral"
                    }

                topic_sentiment[topic][sentiment] += relevance

    for topic, values in topic_sentiment.items():
        dominant = max(
            ["positive", "neutral", "negative", "mixed"],
            key=lambda key: values.get(key, 0)
        )
        values["dominant"] = dominant

        for key in ["positive", "neutral", "negative", "mixed"]:
            values[key] = round(values[key], 2)

    return topic_sentiment


def enrich_item_sentiment(items):
    enriched = []

    for item in items:
        item_copy = dict(item)
        item_copy["item_sentiment"] = classify_item_sentiment(item_copy)
        enriched.append(item_copy)

    return enriched


def split_items_by_relevance(items):
    dashboard_items = []
    background_items = []
    discarded_items = []

    for item in items:
        bucket = item.get("relevance_bucket") or relevance_bucket(item.get("hu_relevance", 0.25))

        if bucket == "dashboard":
            dashboard_items.append(item)
        elif bucket == "background":
            background_items.append(item)
        else:
            discarded_items.append(item)

    return dashboard_items, background_items, discarded_items


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
    all_items = enrich_item_sentiment(all_items)

    all_items.sort(
        key=lambda x: parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True
    )

    dashboard_items, background_items, discarded_items = split_items_by_relevance(all_items)

    index_items = dashboard_items + background_items

    source_counts = {
        "reddit": sum(1 for x in index_items if x.get("source") == "reddit"),
        "youtube": sum(1 for x in index_items if x.get("source") == "youtube"),
        "mastodon": sum(1 for x in index_items if x.get("source") == "mastodon")
    }

    raw_source_counts = {
        "reddit": sum(1 for x in all_items if x.get("source") == "reddit"),
        "youtube": sum(1 for x in all_items if x.get("source") == "youtube"),
        "mastodon": sum(1 for x in all_items if x.get("source") == "mastodon")
    }

    active_sources = sum(1 for value in source_counts.values() if value > 0)

    weighted_mentions = calculate_weighted_mentions(index_items)
    sentiment = detect_sentiment(index_items)
    top_topics = score_topics(index_items)
    topic_sentiment = build_topic_sentiment(index_items)

    return {
        "company": company["company"],
        "social_mentions": len(index_items),
        "raw_social_mentions": len(all_items),
        "dashboard_mentions": len(dashboard_items),
        "background_mentions": len(background_items),
        "discarded_mentions": len(discarded_items),
        "weighted_social_mentions": weighted_mentions,
        "hu_relevant_mentions": len(dashboard_items),
        "social_index": calculate_social_index(weighted_mentions, active_sources, sentiment),
        "social_sources": source_counts,
        "raw_social_sources": raw_source_counts,
        "dominant_social_topic": detect_topic(index_items),
        "top_social_topics": top_topics,
        "topic_sentiment": topic_sentiment,
        "social_sentiment": sentiment,
        "latest_items": dashboard_items[:12],
        "background_items": background_items[:8],
        "quality_summary": {
            "dashboard_items": len(dashboard_items),
            "background_items": len(background_items),
            "discarded_items": len(discarded_items),
            "dashboard_relevance_threshold": DASHBOARD_RELEVANCE_THRESHOLD,
            "background_relevance_threshold": BACKGROUND_RELEVANCE_THRESHOLD
        },
        "method_note": (
            "Nyílt RSS és keresési alapú social signal. "
            "Nem teljes social listening, nem reprezentatív közvélemény-kutatás. "
            "A V1.4 verzió szigorúbb HU relevance szűrést, dashboard/background/discarded bontást "
            "és topic-szintű sentiment mezőt használ."
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
            "raw_social_mentions": result["raw_social_mentions"],
            "dashboard_mentions": result["dashboard_mentions"],
            "background_mentions": result["background_mentions"],
            "discarded_mentions": result["discarded_mentions"],
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


def build_intelligence_summary(results, updated_at):
    if not results:
        return {
            "updated_at": updated_at,
            "leader_social": "n.a.",
            "leader_social_index": 0,
            "dominant_social_topic": "n.a.",
            "overall_social_sentiment": "neutral"
        }

    social_leader = max(results, key=lambda x: x.get("social_index", 0))

    topic_scores = {}
    sentiment_scores = {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
        "mixed": 0
    }

    for result in results:
        for topic in result.get("top_social_topics", []):
            topic_scores[topic["topic"]] = topic_scores.get(topic["topic"], 0) + topic["score"]

        sentiment = result.get("social_sentiment", "neutral")
        sentiment_scores[sentiment] = sentiment_scores.get(sentiment, 0) + 1

    dominant_topic = "n.a."
    if topic_scores:
        dominant_topic = max(topic_scores, key=topic_scores.get)

    overall_sentiment = max(sentiment_scores, key=sentiment_scores.get)

    return {
        "updated_at": updated_at,
        "leader_social": social_leader.get("company", "n.a."),
        "leader_social_index": social_leader.get("social_index", 0),
        "dominant_social_topic": dominant_topic,
        "overall_social_sentiment": overall_sentiment
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    updated_at = now_iso()
    companies = load_company_profiles()
    results = []

    status = {
        "updated_at": updated_at,
        "status": "ok",
        "version": "social-signal-layer-v1.4-quality-topic-sentiment",
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
            "hungarian_relevance_weighting": True,
            "dashboard_relevance_threshold": DASHBOARD_RELEVANCE_THRESHOLD,
            "background_relevance_threshold": BACKGROUND_RELEVANCE_THRESHOLD,
            "discard_below": BACKGROUND_RELEVANCE_THRESHOLD,
            "company_profiles": str(PROFILE_FILE)
        },
        "method_note": (
            "Social Signal Layer V1.4. "
            "Óvatos, nyílt forrású jelzőrendszer szigorúbb HU relevancia-szűréssel, "
            "dashboard/background/discarded bontással és topic-szintű sentiment réteggel."
        )
    }

    for company in companies:
        result = build_company_result(company)
        results.append(result)

        status["companies"].append({
            "company": company["company"],
            "mentions": result["social_mentions"],
            "raw_mentions": result["raw_social_mentions"],
            "dashboard_mentions": result["dashboard_mentions"],
            "background_mentions": result["background_mentions"],
            "discarded_mentions": result["discarded_mentions"],
            "weighted_mentions": result["weighted_social_mentions"],
            "hu_relevant_mentions": result["hu_relevant_mentions"],
            "index": result["social_index"],
            "sources": result["social_sources"],
            "raw_sources": result["raw_social_sources"],
            "sentiment": result["social_sentiment"],
            "topic": result["dominant_social_topic"],
            "errors": result["errors"]
        })

    payload = {
        "updated_at": updated_at,
        "version": "social-signal-layer-v1.4-quality-topic-sentiment",
        "scope": "Hungarian FMCG retail chains",
        "method_note": (
            "Ez social signal réteg, nem teljes social analytics. "
            "A mutató friss, nyílt forrású említésekből készül, "
            "company-profiles.json alapú magyar piaci relevancia-szűréssel. "
            "A V1.4 verzió csak dashboard és background relevanciájú elemeket számol az indexbe."
        ),
        "intelligence_summary": build_intelligence_summary(results, updated_at),
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
