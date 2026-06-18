#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Employee Review Collector v7

Cél:
- Valódi dolgozói vélemények gyűjtése közvetlen, előre ismert publikus forrásoldalakról.
- Google News nincs.
- LinkedIn nincs.
- Keresőmotor nincs.
- Reddit keresés megmarad, de a fő adatforrás a direkt URL-lista.

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
    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
)

REQUEST_TIMEOUT = 30
SLEEP_MIN = 2.0
SLEEP_MAX = 5.0

MAX_ITEMS_PER_COMPANY = 40
MAX_EXCLUDED_PER_COMPANY = 80
MAX_QUOTE_LENGTH = 700


COMPANIES = {
    "Auchan": ["Auchan", "AUCHAN", "Auchan Magyarország"],
    "Lidl": ["Lidl", "LIDL", "Lidl Magyarország"],
    "Aldi": ["Aldi", "ALDI", "ALDI Magyarország"],
    "Penny": ["Penny", "PENNY", "Penny Market", "Penny-Market"],
    "Spar": ["Spar", "SPAR", "SPAR Magyarország"],
    "Tesco": ["Tesco", "TESCO", "Tesco Magyarország"],
}


DIRECT_REVIEW_URLS = {
    "Auchan": [
        "https://www.profession.hu/cegek/auchan-magyarorszag-kft/velemenyek",
        "https://www.profession.hu/cegek/auchan-magyarorszag-kft/ertekelesek",
    ],
    "Lidl": [
        "https://www.profession.hu/cegek/lidl-magyarorszag-bt/velemenyek",
        "https://www.profession.hu/cegek/lidl-magyarorszag-bt/ertekelesek",
        "https://www.gyakorikerdesek.hu/uzlet-es-penzugyek__karrier-fizetes__11120824-lidl-ben-mennyit-keres-pontosan-egy-bolti-alkalmazott",
        "https://www.gyakorikerdesek.hu/uzlet-es-penzugyek__karrier-fizetes__12023812-ezek-utan-ha-nem-akarok-ott-dolgozni-ertheto-lidl",
        "https://www.gyakorikerdesek.hu/uzlet-es-penzugyek__karrier-fizetes__12662254-mennyi-a-fizetes-a-lidl-ben-4-oras-munkaidoben",
    ],
    "Aldi": [
        "https://www.profession.hu/cegek/aldi-magyarorszag-elelmiszer-bt/velemenyek",
        "https://www.profession.hu/cegek/aldi-magyarorszag-elelmiszer-bt/ertekelesek",
    ],
    "Penny": [
        "https://www.profession.hu/cegek/penny-market-kft/velemenyek",
        "https://www.profession.hu/cegek/penny-market-kft/ertekelesek",
        "https://www.gyakorikerdesek.hu/emberek__munkahely-kollegak__13163147-a-tesco-lidl-spar-penny-negyes-kozul-melyikben-a-legjobb-dolgozni",
    ],
    "Spar": [
        "https://www.profession.hu/cegek/spar-magyarorszag-kft/velemenyek",
        "https://www.profession.hu/cegek/spar-magyarorszag-kft/ertekelesek",
        "https://www.gyakorikerdesek.hu/emberek__munkahely-kollegak__13163147-a-tesco-lidl-spar-penny-negyes-kozul-melyikben-a-legjobb-dolgozni",
    ],
    "Tesco": [
        "https://www.profession.hu/cegek/tesco-zrt/velemenyek",
        "https://www.profession.hu/cegek/tesco-bst-zrt/velemenyek",
        "https://www.profession.hu/cegek/tesco-global-zrt/ertekelesek",
        "https://www.gyakorikerdesek.hu/uzlet-es-penzugyek__karrier-fizetes__7340152-tenyleg-ennyire-kegyetlen-a-tesco-ban-dolgozni",
        "https://www.gyakorikerdesek.hu/emberek__munkahely-kollegak__10813380-nagyon-gaz-a-tescoban-dolgozni",
        "https://www.gyakorikerdesek.hu/emberek__munkahely-kollegak__13163147-a-tesco-lidl-spar-penny-negyes-kozul-melyikben-a-legjobb-dolgozni",
    ],
}


TOPIC_KEYWORDS = {
    "bérezés": [
        "fizetés", "bér", "bérezés", "órabér", "kereset", "jövedelem",
        "nettó", "bruttó", "pénz", "javadalmazás", "alulfizetett"
    ],
    "juttatások": [
        "cafeteria", "juttatás", "bónusz", "prémium", "kedvezmény",
        "utalvány", "jutalom"
    ],
    "munkaterhelés": [
        "sok munka", "leterhelt", "túlterhelt", "hajtás", "fárasztó",
        "kevés ember", "létszámhiány", "tempó", "pörgés", "pakolás",
        "kiszajtolják", "kisajtolják", "fizikailag megterhelő"
    ],
    "beosztás": [
        "beosztás", "műszak", "hétvége", "túlóra", "munkaidő",
        "éjszaka", "vasárnap", "szabadnap", "váltás", "munkarend"
    ],
    "vezetés": [
        "vezető", "főnök", "menedzser", "felettes", "boltvezető",
        "osztályvezető", "vezetőség", "kommunikáció", "motíváltak",
        "motiváltak"
    ],
    "csapat": [
        "csapat", "kolléga", "munkatárs", "közösség", "brigád",
        "jó hangulat", "segítőkész"
    ],
    "előrelépés": [
        "karrier", "előrelépés", "fejlődés", "betanítás", "képzés",
        "előmenetel", "fejlődési"
    ],
    "munkahelyi légkör": [
        "stressz", "légkör", "hangulat", "megbecsülés", "nyomás",
        "konfliktus", "kiégés", "magánélet", "munka-magánélet"
    ],
}


POSITIVE_WORDS = [
    "jó", "korrekt", "pozitív", "segítőkész", "stabil", "rugalmas",
    "elégedett", "ajánlom", "jó csapat", "jó hely", "összetartó",
    "barátságos", "fejlődés", "lehetőség"
]

NEGATIVE_WORDS = [
    "rossz", "kevés", "alacsony", "nehéz", "stressz", "túlóra",
    "létszámhiány", "fárasztó", "nem ajánlom", "felmondtam",
    "borzalmas", "kegyetlen", "kisajtolják", "nincs egyensúlyban",
    "problémás", "feszes", "utolsó másodpercben"
]


REVIEW_SIGNALS = [
    "jelenlegi munkavállaló",
    "korábbi munkavállaló",
    "dolgoztam",
    "dolgozom",
    "dolgozott",
    "dolgozik",
    "munkahely",
    "munkavállaló",
    "munkatárs",
    "kolléga",
    "főnök",
    "vezető",
    "beosztás",
    "műszak",
    "munkaidő",
    "munkarend",
    "fizetés",
    "bér",
    "juttatás",
    "pozitívumok",
    "negatívumok",
    "tapasztalat",
    "vélemény",
    "értékelés",
    "munka és magánélet",
    "kollégák és céges hangulat",
    "főnökök",
    "munkaidő és munkarend",
    "bérezés és juttatások",
]


HARD_EXCLUDE_TERMS = [
    "lejárt a munkameneted",
    "belépés",
    "ezt a véleményt már jelentették",
    "rendben",
    "értékelje és mondja el véleményét",
    "értékeld és mondd el véleményedet",
    "segítsen és értékelje",
    "írjon saját értékelést",
    "cookie",
    "javascript",
    "adatvédelmi",
    "állások",
    "álláshirdetés",
    "karrier lehetőség",
    "friss állás",
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


def review_score(text: str) -> int:
    lower = text.lower()
    score = 0

    for signal in REVIEW_SIGNALS:
        if signal in lower:
            score += 2

    if "pozitívumok" in lower:
        score += 3

    if "negatívumok" in lower:
        score += 3

    if "jelenlegi munkavállaló" in lower or "korábbi munkavállaló" in lower:
        score += 5

    return score


def has_hard_exclusion(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in HARD_EXCLUDE_TERMS)


def exclusion_reason(text: str, company: str) -> Optional[str]:
    text = clean_text(text)

    if len(text) < 55:
        return "too_short"

    if len(text.split()) < 7:
        return "too_few_words"

    if not contains_company(text, company):
        return "company_not_found"

    if has_hard_exclusion(text):
        return "hard_excluded_ui_or_job_content"

    if review_score(text) < 4:
        return "weak_review_signal"

    return None


def classify_topic(text: str) -> str:
    lower = text.lower()
    scores = {}

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


def extract_profession_review_blocks(html_text: str) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    text = clean_text(soup.get_text(" ", strip=True))

    blocks = []

    patterns = [
        r"(?:##\s*)?(.{20,350}?)(Jelenlegi munkavállaló|Korábbi munkavállaló).{0,350}?(?=(?:##\s*)?.{10,220}?(?:Jelenlegi munkavállaló|Korábbi munkavállaló)|$)",
        r"(Pozitívumok.{10,350}?Negatívumok.{10,500}?)(?=Pozitívumok|Negatívumok|Értékelés kategóriák|$)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            block = clean_text(match.group(0))
            if len(block) >= 60:
                blocks.append(block)

    headings = soup.find_all(["h1", "h2", "h3", "p", "li", "div"])

    for node in headings:
        node_text = clean_text(node.get_text(" ", strip=True))

        if len(node_text) < 60:
            continue

        lower = node_text.lower()

        if (
            "jelenlegi munkavállaló" in lower
            or "korábbi munkavállaló" in lower
            or "pozitívumok" in lower
            or "negatívumok" in lower
        ):
            blocks.append(node_text)

    return deduplicate_texts(blocks)


def extract_gyakori_blocks(html_text: str) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    blocks = []

    selectors = [
        ".kerdes",
        ".valasz",
        ".answer",
        ".question",
        "article",
        "p",
        "div",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))

            if len(text) >= 80:
                blocks.append(text)

    return deduplicate_texts(blocks)


def extract_generic_blocks(html_text: str) -> List[str]:
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    blocks = []

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
        "div",
    ]

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))

            if len(text) >= 80:
                blocks.append(text)

    return deduplicate_texts(blocks)


def extract_blocks_from_page(url: str, html_text: str) -> List[str]:
    lower_url = url.lower()

    if "profession.hu" in lower_url:
        return extract_profession_review_blocks(html_text)

    if "gyakorikerdesek.hu" in lower_url:
        return extract_gyakori_blocks(html_text)

    return extract_generic_blocks(html_text)


def deduplicate_texts(texts: List[str]) -> List[str]:
    seen = set()
    result = []

    for text in texts:
        key = make_hash(text)

        if key in seen:
            continue

        seen.add(key)
        result.append(text)

    return result


def build_item(company: str, source: str, url: str, raw_text: str) -> Optional[Dict[str, Any]]:
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
        "published_or_found_date": "",
        "date_collected": now_iso(),
        "topic": classify_topic(quote),
        "sentiment": classify_sentiment(quote),
        "quote": quote,
        "length": len(quote),
        "review_signal_score": score,
        "confidence": "high" if score >= 10 else "medium",
        "privacy_note": "Személyes adatok automatikusan eltávolítva, ha felismerhetőek voltak.",
    }


def build_excluded_item(company: str, source: str, url: str, raw_text: str, reason: str) -> Dict[str, Any]:
    quote = normalize_quote(raw_text)

    return {
        "id": make_hash("excluded" + company + source + url + quote),
        "company": company,
        "source": source,
        "source_url": url,
        "date_collected": now_iso(),
        "reason": reason,
        "quote": quote,
        "length": len(quote),
    }


def process_block(
    company: str,
    source: str,
    url: str,
    block: str,
    valid: List[Dict[str, Any]],
    excluded: List[Dict[str, Any]],
) -> None:
    reason = exclusion_reason(block, company)

    if reason:
        excluded.append(
            build_excluded_item(
                company=company,
                source=source,
                url=url,
                raw_text=block,
                reason=reason,
            )
        )
        return

    item = build_item(company, source, url, block)

    if item:
        valid.append(item)


def reddit_search(query: str) -> List[Dict[str, str]]:
    url = f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=new&limit=20"

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
            body = clean_text(post.get("selftext", ""))
            permalink = post.get("permalink", "")

            if not title and not body:
                continue

            link = f"https://www.reddit.com{permalink}" if permalink else ""

            results.append(
                {
                    "url": link,
                    "text": clean_text(f"{title}. {body}"),
                }
            )

    except Exception as error:
        print(f"  reddit parse failed: {query} | {error}")

    return results


def collect_reddit(company: str, aliases: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    valid = []
    excluded = []

    for alias in aliases:
        queries = [
            f'"{alias}" dolgoztam',
            f'"{alias}" dolgozom',
            f'"{alias}" munkahely',
            f'"{alias}" fizetés',
            f'"{alias}" műszak',
            f'"{alias}" nem ajánlom',
        ]

        for query in queries:
            print(f"  Reddit query: {query}")

            for result in reddit_search(query):
                process_block(
                    company=company,
                    source="reddit_public_search",
                    url=result.get("url", ""),
                    block=result.get("text", ""),
                    valid=valid,
                    excluded=excluded,
                )

    return {
        "valid": valid,
        "excluded": excluded,
    }


def collect_direct_urls(company: str) -> Dict[str, List[Dict[str, Any]]]:
    valid = []
    excluded = []

    urls = DIRECT_REVIEW_URLS.get(company, [])

    for url in urls:
        print(f"  Reading direct review source: {url}")

        html_text = request_url(url)
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        if not html_text:
            continue

        blocks = extract_blocks_from_page(url, html_text)

        source = "profession_direct_review_page"
        if "gyakorikerdesek.hu" in url.lower():
            source = "gyakorikerdesek_direct_page"

        for block in blocks:
            process_block(
                company=company,
                source=source,
                url=url,
                block=block,
                valid=valid,
                excluded=excluded,
            )

    return {
        "valid": valid,
        "excluded": excluded,
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


def build_output(valid_items: List[Dict[str, Any]], excluded_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        "method": "direct_profession_gyakorikerdesek_reddit_v7",
        "important_note": (
            "A rendszer közvetlen, előre ismert publikus véleményoldalakat használ. "
            "Google News, LinkedIn és keresőmotoros scraping nincs használatban."
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

        direct_result = collect_direct_urls(company)
        reddit_result = collect_reddit(company, aliases)

        company_valid = []
        company_excluded = []

        company_valid.extend(direct_result["valid"])
        company_valid.extend(reddit_result["valid"])

        company_excluded.extend(direct_result["excluded"])
        company_excluded.extend(reddit_result["excluded"])

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
    print("Employee Review Collector v7 started.")

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
