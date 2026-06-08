import json
import re
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

COMPANIES_FILE = DATA_DIR / "companies.json"
OUTPUT_FILE = DATA_DIR / "news-social.json"
STATUS_FILE = DATA_DIR / "news-social-status.json"
HISTORY_DIR = DATA_DIR / "news-social-history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

TODAY = datetime.now(timezone.utc)
DAYS_BACK = 30


SOURCE_QUERIES = [
    "{company} élelmiszer kiskereskedelem",
    "{company} áruház Magyarország",
    "{company} akció árak",
    "{company} munkaerő bér állás",
    "{company} beruházás üzletnyitás",
]


NARRATIVE_KEYWORDS = {
    "árverseny": ["ár", "akció", "olcsó", "infláció", "drágulás", "kedvezmény"],
    "munkaerő": ["munkaerő", "bér", "fizetés", "állás", "dolgozó", "sztrájk"],
    "terjeszkedés": ["új üzlet", "üzletnyitás", "beruházás", "fejlesztés", "logisztikai központ"],
    "fenntarthatóság": ["fenntartható", "zöld", "energia", "napelem", "környezet"],
    "beszállítók": ["beszállító", "ellátási lánc", "termelő", "hazai termék"],
    "reputációs kockázat": ["bírság", "hatóság", "panasz", "botrány", "visszahívás", "NAV", "GVH"]
}

POSITIVE_WORDS = [
    "fejlesztés", "beruházás", "nyitás", "bővítés", "növekedés",
    "kedvezmény", "elismerés", "díj", "fenntartható", "támogatás"
]

NEGATIVE_WORDS = [
    "bírság", "panasz", "botrány", "bezárás", "veszteség", "drágulás",
    "sztrájk", "munkaerőhiány", "visszahívás", "hatóság", "GVH", "NAV"
]


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_google_news_rss(query):
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=hu&gl=HU&ceid=HU:hu"


def entry_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return TODAY


def article_id(company_id, title, link):
    raw = f"{company_id}|{title}|{link}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def classify_sentiment(text):
    lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w.lower() in lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w.lower() in lower)

    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def detect_narratives(text):
    lower = text.lower()
    found = []

    for narrative, words in NARRATIVE_KEYWORDS.items():
        if any(w.lower() in lower for w in words):
            found.append(narrative)

    return found or ["általános"]


def risk_score(articles):
    if not articles:
        return 0

    negative = sum(1 for a in articles if a["sentiment"] == "negative")
    risk_mentions = sum(
        1 for a in articles
        if "reputációs kockázat" in a["narratives"]
    )

    score = min(100, round((negative * 18) + (risk_mentions * 14)))
    return score


def company_queries(company):
    return [q.format(company=company) for q in SOURCE_QUERIES]


def collect_company(company):
    company_id = company.get("id")
    company_name = company.get("company") or company.get("name")

    articles_by_id = {}

    for query in company_queries(company_name):
        rss_url = make_google_news_rss(query)
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            title = clean_text(getattr(entry, "title", ""))
            summary = clean_text(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            source = getattr(getattr(entry, "source", None), "title", None)

            published_at = entry_date(entry)

            if published_at < TODAY - timedelta(days=DAYS_BACK):
                continue

            full_text = f"{title} {summary}"
            narratives = detect_narratives(full_text)
            sentiment = classify_sentiment(full_text)

            item = {
                "id": article_id(company_id, title, link),
                "company_id": company_id,
                "company": company_name,
                "title": title,
                "summary": summary,
                "url": link,
                "source": source or "Google News",
                "published_at": published_at.strftime("%Y-%m-%d"),
                "sentiment": sentiment,
                "narratives": narratives,
                "query": query
            }

            articles_by_id[item["id"]] = item

    articles = list(articles_by_id.values())
    articles.sort(key=lambda x: x["published_at"], reverse=True)

    last_7 = [
        a for a in articles
        if datetime.fromisoformat(a["published_at"]).replace(tzinfo=timezone.utc) >= TODAY - timedelta(days=7)
    ]

    sentiment_counts = {
        "positive": sum(1 for a in articles if a["sentiment"] == "positive"),
        "neutral": sum(1 for a in articles if a["sentiment"] == "neutral"),
        "negative": sum(1 for a in articles if a["sentiment"] == "negative")
    }

    narrative_counts = {}
    for a in articles:
        for n in a["narratives"]:
            narrative_counts[n] = narrative_counts.get(n, 0) + 1

    dominant_narrative = None
    if narrative_counts:
        dominant_narrative = max(narrative_counts.items(), key=lambda x: x[1])[0]

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "news_count_7d": len(last_7),
        "news_count_30d": len(articles),
        "social_mentions": None,
        "social_signal_status": "not_collected",
        "positive_count": sentiment_counts["positive"],
        "neutral_count": sentiment_counts["neutral"],
        "negative_count": sentiment_counts["negative"],
        "risk_score": risk_score(articles),
        "dominant_narrative": dominant_narrative or "n.a.",
        "narratives": narrative_counts,
        "source_confidence": "medium" if articles else "low",
        "articles": articles[:20]
    }


def build_weekly_insight(companies):
    if not companies:
        return "Nincs elérhető híranyag az aktuális időszakban."

    by_news = sorted(companies, key=lambda x: x["news_count_30d"], reverse=True)
    by_risk = sorted(companies, key=lambda x: x["risk_score"], reverse=True)
    by_positive = sorted(companies, key=lambda x: x["positive_count"], reverse=True)

    top_news = by_news[0]
    top_risk = by_risk[0]
    top_positive = by_positive[0]

    return (
        f"Az elmúlt 30 nap nyilvános hírforrásai alapján a legnagyobb médiaaktivitás "
        f"{top_news['company']} körül látható, {top_news['news_count_30d']} azonosított megjelenéssel. "
        f"A legmagasabb reputációs kockázati jelzés {top_risk['company']} esetében jelent meg, "
        f"{top_risk['risk_score']}/100 értékkel. "
        f"A legtöbb pozitív jellegű említés {top_positive['company']} oldalán látható. "
        f"A social media adatgyűjtés ebben a verzióban még nem aktív, ezért a social signal külön fejlesztési körben kezelendő."
    )


def main():
    companies = load_json(COMPANIES_FILE, [])

    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/companies.json fájl.")

    collected = []

    for company in companies:
        collected.append(collect_company(company))

    output = {
        "snapshot_date": TODAY.strftime("%Y-%m-%d"),
        "mode": "public_news_rss_collection_v1",
        "social_status": "not_collected",
        "companies": collected,
        "weekly_insight": build_weekly_insight(collected),
        "notes": (
            "Az adatok Google News RSS keresésekből származó nyilvános hírmegjelenések. "
            "A sentiment és narrative kategorizálás egyszerű kulcsszavas előzetes osztályozás, "
            "nem teljes AI-minősítés. A social media adatok ebben a verzióban még nem kerülnek gyűjtésre."
        )
    }

    save_json(OUTPUT_FILE, output)

    history_file = HISTORY_DIR / f"{TODAY.strftime('%Y-%m')}.json"
    save_json(history_file, output)

    status = {
        "last_update": TODAY.strftime("%Y-%m-%d"),
        "companies_tracked": len(collected),
        "mode": "public_news_rss_collection_v1",
        "output_file": "news-social.json",
        "history_file": f"{TODAY.strftime('%Y-%m')}.json",
        "social_status": "not_collected"
    }

    save_json(STATUS_FILE, status)

    print("News & Social Monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
