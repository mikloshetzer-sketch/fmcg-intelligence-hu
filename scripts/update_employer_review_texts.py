#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Intelligence Hungary
Employee Review Collector v5

Cél:
- Valódi dolgozói vélemények keresése.
- Google News és LinkedIn kizárva.
- Régi hibás találatok nem kerülnek továbbmentésre.
- Első körben:
  1. Reddit publikus keresés
  2. Profession publikus értékelési/munkaadói oldalak keresése
  3. Kézzel megadható publikus vélemény URL-ek

Kimenet:
docs/data/employer-review-texts.json
"""

import json
import re
import time
import random
import hashlib
import html
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
SLEEP_MIN = 2.0
SLEEP_MAX = 5.0

MAX_ITEMS_PER_COMPANY = 30
MAX_EXCLUDED_PER_COMPANY = 40
MAX_QUOTE_LENGTH = 500


COMPANIES = {
    "Auchan": ["Auchan", "Auchan Magyarország"],
    "Lidl": ["Lidl", "Lidl Magyarország"],
    "Aldi": ["Aldi", "ALDI", "ALDI Magyarország"],
    "Penny": ["Penny", "PENNY", "Penny Market", "PENNY Magyarország"],
    "Spar": ["Spar", "SPAR", "SPAR Magyarország"],
    "Tesco": ["Tesco", "Tesco Magyarország"],
}


MANUAL_REVIEW_URLS = {
    "Auchan": [],
    "Lidl": [],
    "Aldi": [],
    "Penny": [],
    "Spar": [],
    "Tesco": [],
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "bérezés", "órabér", "kereset", "jövedelem",
        "nettó", "bruttó", "pénz", "keveset fizetnek", "alulfizetett"
    ],
    "juttatások": [
        "cafeteria", "juttatás", "bónusz", "prémium", "kedvezmény",
        "utalvány", "jutalom"
    ],
    "munkaterhelés": [
        "sok munka", "leterhelt", "túlterhelt", "hajtás", "fárasztó",
        "kevés ember", "létszámhiány", "tempó", "pörgés", "robot",
        "széthajtják", "pakolás"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "munkaidő",
        "éjszaka", "vasárnap", "szabadnap", "váltás"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "felettes", "boltvezető",
        "osztályvezető", "vezetőség", "kommunikáció"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "brigád",
        "jó hangulat", "segítőkész"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "betanítás",
        "képzés", "tanulás", "előmenetel"
    ],
    "munkahelyi légkör": [
        "stressz", "légkör", "hangulat", "megbecsülés", "tisztelet",
        "nyomás", "konfliktus", "kiégés", "mérgező"
    ],
}


POSITIVE_WORDS = [
    "jó", "korrekt", "pozitív", "segítőkész", "stabil", "rugalmas",
    "barátságos", "megbecsül", "támogató", "elégedett", "szeretek",
    "ajánlom", "jó csapat", "jó hely", "rendben van"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "leterhelt", "létszámhiány", "fárasztó", "probléma", "gyenge",
    "elégedetlen", "nyomás", "konfliktus", "kaotikus", "nem ajánlom",
    "széthajtják", "kizsigerel", "borzalmas", "felmondtam"
]


REVIEW_STRONG_SIGNALS = [
    "dolgoztam",
    "dolgozom",
    "ott dolgoztam",
    "ott dolgozom",
    "náluk dolgoztam",
    "náluk dolgozom",
    "munkatársként",
    "eladóként",
    "pénztárosként",
    "árufeltöltőként",
    "raktárosként",
    "vezetőként",
    "tapasztalatom",
    "az én tapasztalatom",
    "saját tapasztalat",
    "felmondtam",
    "kiléptem",
    "nem ajánlom",
    "ajánlom",
]


REVIEW_WEAK_SIGNALS = [
    "munkahely",
    "munkavállaló",
    "dolgozó",
    "munkatárs",
    "kolléga",
    "főnök",
    "vezető",
    "beosztás",
    "műszak",
    "túlóra",
    "fizetés",
    "bér",
    "cafeteria",
    "létszámhiány",
    "stressz",
    "munkaterhelés",
    "hangulat",
    "csapat",
    "vélemény",
    "tapasztalat",
]


EXCLUDED_TERMS = [
    "béremelés",
    "bérfejlesztés",
    "emeli a béreket",
    "emel a fizetéseken",
    "fizetésemelés",
    "juttatási csomag",
    "egészségprogram",
    "állások, karrier",
    "álláshirdetés",
    "állások",
    "szezonális állások",
    "felvételét tervezik",
    "közlemény",
    "sajtóközlemény",
    "hvg.hu",
    "pénzcentrum",
    "portfolio.hu",
    "24.hu",
    "blikk",
    "index.hu",
    "világgazdaság",
    "trade magazin",
    "hr portál",
    "onbrands",
    "mindmegette",
    "nool",
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

    return clean_text(text)


def normalize_quote(text: str) -> str:
    text = remove_personal_data(text)

    if len(text) > MAX_QUOTE_LENGTH:
        text = text[:MAX_QUOTE_LENGTH].rsplit(" ", 1)[0] + "..."

    return text


def contains_company(text: str, company: str) -> bool:
    lower = text.lower()
    aliases = COMPANIES.get(company, [company])
    return any(alias.lower() in lower for alias in aliases)


def has_excluded_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in EXCLUDED_TERMS)


def review_score(text: str) -> int:
    lower = text.lower()

    score = 0
    score += sum(3 for signal in REVIEW_STRONG_SIGNALS if signal in lower)
    score += sum(1 for signal in REVIEW_WEAK_SIGNALS if signal in lower)

    if "?" in text:
        score += 1

    return score


def exclusion_reason(text: str, company: str) -> Optional[str]:
    text = clean_text(text)

    if len(text) < 80:
        return "too_short"

    if len(text.split()) < 12:
        return "too_few_words"

    if not contains_company(text, company):
        return "company_not_found"

    if has_excluded_terms(text):
        return "news_or_job_content"

    if review_score(text) < 5:
        return "weak_review_signal"

    return None


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


def reddit_search(query: str) -> List[Dict[str, str]]:
    encoded = quote_plus(query)
    url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit=25"

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
            created = str(post.get("created_utc", ""))

            if not title and not selftext:
                continue

            link = f"https://www.reddit.com{permalink}" if permalink else ""

            results.append({
                "source": "reddit_public_search",
                "title": title,
                "body": selftext,
                "url": link,
                "date": created,
            })

    except Exception as error:
        print(f"  reddit parse failed: {query} | {error}")

    return results


def extract_text_blocks_from_page(url: str) -> List[str]:
    html_text = request_url(url)
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")

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

    blocks = []
    seen = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            key = make_hash(text)

            if key in seen:
                continue

            seen.add(key)
            blocks.append(text)

    return blocks


def build_item(
    company: str,
    source: str,
    url: str,
    raw_text: str,
    date: str = "",
) -> Optional[Dict[str, Any]]:
    quote = normalize_quote(raw_text)
    reason = exclusion_reason(quote, company)

    if reason:
        return None

    score = review_score(quote)

    return {
        "id": make_hash(company + source + url + quote),
        "company": company,
        "source": source,
        "source_url": url,
        "published_or_found_date": date,
        "date_collected": now_iso(),
        "topic": classify_topic(quote),
        "sentiment": classify_sentiment(quote),
        "quote": quote,
        "length": len(quote),
        "review_signal_score": score,
        "confidence": "high" if score >= 8 else "medium",
        "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
    }


def build_excluded_item(
    company: str,
    source: str,
    url: str,
    raw_text: str,
    reason: str,
    date: str = "",
) -> Dict[str, Any]:
    quote = normalize_quote(raw_text)

    return {
        "id": make_hash("excluded" + company + source + url + quote),
        "company": company,
        "source": source,
        "source_url": url,
        "published_or_found_date": date,
        "date_collected": now_iso(),
        "reason": reason,
        "quote": quote,
        "length": len(quote),
    }


def collect_reddit_for_company(company: str, aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    queries = []

    for alias in aliases:
        queries.extend([
            f'"{alias}" dolgoztam',
            f'"{alias}" dolgozom',
            f'"{alias}" munkahely',
            f'"{alias}" fizetés',
            f'"{alias}" műszak',
            f'"{alias}" főnök',
            f'"{alias}" nem ajánlom',
            f'"{alias}" tapasztalat',
        ])

    valid_items = []
    excluded_items = []

    for query in queries:
        print(f"  Reddit query: {query}")

        results = reddit_search(query)

        for result in results:
            raw_text = clean_text(f"{result.get('title', '')}. {result.get('body', '')}")
            url = result.get("url", "")
            date = result.get("date", "")

            reason = exclusion_reason(raw_text, company)

            if reason:
                excluded_items.append(
                    build_excluded_item(
                        company=company,
                        source="reddit_public_search",
                        url=url,
                        raw_text=raw_text,
                        reason=reason,
                        date=date,
                    )
                )
                continue

            item = build_item(
                company=company,
                source="reddit_public_search",
                url=url,
                raw_text=raw_text,
                date=date,
            )

            if item:
                valid_items.append(item)

    return {
        "valid": valid_items,
        "excluded": excluded_items,
    }


def collect_manual_urls_for_company(company: str) -> Dict[str, List[Dict[str, Any]]]:
    urls = MANUAL_REVIEW_URLS.get(company, [])

    valid_items = []
    excluded_items = []

    for url in urls:
        print(f"  Manual review URL: {url}")

        blocks = extract_text_blocks_from_page(url)

        for block in blocks:
            reason = exclusion_reason(block, company)

            if reason:
                excluded_items.append(
                    build_excluded_item(
                        company=company,
                        source="manual_public_review_url",
                        url=url,
                        raw_text=block,
                        reason=reason,
                    )
                )
                continue

            item = build_item(
                company=company,
                source="manual_public_review_url",
                url=url,
                raw_text=block,
            )

            if item:
                valid_items.append(item)

    return {
        "valid": valid_items,
        "excluded": excluded_items,
    }


def deduplicate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []

    for item in items:
        key = item.get("id") or make_hash(item.get("quote", ""))

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def summarize_company(
    company: str,
    valid_items: List[Dict[str, Any]],
    excluded_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    company_valid = [item for item in valid_items if item.get("company") == company]
    company_excluded = [item for item in excluded_items if item.get("company") == company]

    topic_counts: Dict[str, int] = {}
    sentiment_counts = {
        "positive": 0,
        "neutral": 0,
        "negative": 0,
    }
    source_counts: Dict[str, int] = {}
    exclusion_counts: Dict[str, int] = {}

    for item in company_valid:
        topic = item.get("topic", "általános munkáltatói tapasztalat")
        sentiment = item.get("sentiment", "neutral")
        source = item.get("source", "unknown")

        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        if sentiment not in sentiment_counts:
            sentiment = "neutral"

        sentiment_counts[sentiment] += 1

    for item in company_excluded:
        reason = item.get("reason", "unknown")
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

    return {
        "company": company,
        "review_text_count": len(company_valid),
        "excluded_count": len(company_excluded),
        "dominant_topics": [
            {"topic": topic, "count": count}
            for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        ],
        "sentiment_counts": sentiment_counts,
        "source_counts": [
            {"source": source, "count": count}
            for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
        ],
        "exclusion_counts": [
            {"reason": reason, "count": count}
            for reason, count in sorted(exclusion_counts.items(), key=lambda x: x[1], reverse=True)
        ],
        "sample_quotes": company_valid[:5],
        "sample_excluded": company_excluded[:3],
    }


def build_output(
    valid_items: List[Dict[str, Any]],
    excluded_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if valid_items:
        status = "ok"
    elif excluded_items:
        status = "no_valid_employee_reviews_only_excluded_items"
    else:
        status = "no_results_found"

    return {
        "updated_at": now_iso(),
        "status": status,
        "source_type": "public_osint_employee_reviews",
        "method": "reddit_and_manual_public_review_sources_v5",
        "important_note": (
            "Ez a fájl kizárólag valódi dolgozói vélemény jellegű szövegek gyűjtésére készült. "
            "Google News és LinkedIn nincs használatban. A rendszer inkább üres items tömböt ad vissza, "
            "mint hogy bérhíreket, sajtócikkeket vagy álláshirdetéseket dolgozói véleményként kezeljen."
        ),
        "privacy_note": (
            "A script automatikusan eltávolítja az e-mail címeket és telefonszámokat. "
            "Személyes adatot nem szabad menteni."
        ),
        "companies": [
            summarize_company(company, valid_items, excluded_items)
            for company in COMPANIES.keys()
        ],
        "items": valid_items,
        "excluded_items": excluded_items,
    }


def collect_all() -> Dict[str, List[Dict[str, Any]]]:
    all_valid = []
    all_excluded = []

    for company, aliases in COMPANIES.items():
        print(f"Collecting employee reviews for: {company}")

        reddit_result = collect_reddit_for_company(company, aliases)
        manual_result = collect_manual_urls_for_company(company)

        company_valid = []
        company_excluded = []

        company_valid.extend(reddit_result["valid"])
        company_valid.extend(manual_result["valid"])

        company_excluded.extend(reddit_result["excluded"])
        company_excluded.extend(manual_result["excluded"])

        company_valid = deduplicate_items(company_valid)[:MAX_ITEMS_PER_COMPANY]
        company_excluded = deduplicate_items(company_excluded)[:MAX_EXCLUDED_PER_COMPANY]

        print(f"  valid reviews: {len(company_valid)}")
        print(f"  excluded: {len(company_excluded)}")

        all_valid.extend(company_valid)
        all_excluded.extend(company_excluded)

    return {
        "valid": deduplicate_items(all_valid),
        "excluded": deduplicate_items(all_excluded),
    }


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main() -> None:
    print("Employee Review Collector v5 started.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    collected = collect_all()

    output = build_output(
        valid_items=collected["valid"],
        excluded_items=collected["excluded"],
    )

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Valid review items: {len(collected['valid'])}")
    print(f"Excluded items: {len(collected['excluded'])}")
    print(f"Status: {output['status']}")


if __name__ == "__main__":
    main()
