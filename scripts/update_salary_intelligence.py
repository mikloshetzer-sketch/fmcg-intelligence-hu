#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Intelligence v1

Cél:
- FMCG szereplők fizetési információinak kiegészítő ellenőrzése.
- Nem váltja ki a salaries.json fájlt, hanem mellé készít kontroll-adatbázist.
- Forráslogika:
  1. meglévő salaries.json
  2. meglévő job-postings-current.json
  3. szakmai/üzleti média RSS és publikus oldalak:
     Trade Magazin, Portfolio, Pénzcentrum, HR Portal, 24.hu, HVG
- Kimenet:
  docs/data/salary-intelligence.json
"""

import json
import re
import time
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from html import unescape


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

SALARIES_FILE = DATA_DIR / "salaries.json"
POSTINGS_FILE = DATA_DIR / "job-postings-current.json"
OUTPUT_FILE = DATA_DIR / "salary-intelligence.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/125 Safari/537.36"
)

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 2

COMPANIES = {
    "lidl": "Lidl",
    "aldi": "ALDI",
    "spar": "SPAR",
    "tesco": "Tesco",
    "penny": "PENNY",
    "auchan": "Auchan",
}

ROLE_MAP = {
    "cashier_huf_month": {
        "label": "Pénztáros",
        "keywords": ["pénztáros", "kasszás", "eladó-pénztáros", "eladó pénztáros"],
    },
    "stocker_huf_month": {
        "label": "Árufeltöltő",
        "keywords": ["árufeltöltő", "bolti dolgozó", "bolti munkatárs", "eladó"],
    },
    "bakery_worker_huf_month": {
        "label": "Pék / pékáru dolgozó",
        "keywords": ["pék", "pékáru", "pékség", "bakery"],
    },
    "shift_leader_huf_month": {
        "label": "Műszakvezető",
        "keywords": ["műszakvezető", "műszak vezető", "shift leader"],
    },
    "department_manager_huf_month": {
        "label": "Osztályvezető / részlegvezető",
        "keywords": ["osztályvezető", "részlegvezető", "csoportvezető"],
    },
    "store_manager_huf_month": {
        "label": "Áruházvezető / üzletvezető",
        "keywords": ["áruházvezető", "üzletvezető", "boltvezető", "store manager"],
    },
    "warehouse_worker_huf_month": {
        "label": "Raktári dolgozó",
        "keywords": ["raktári dolgozó", "raktáros", "targoncavezető", "komissiózó"],
    },
    "office_specialist_huf_month": {
        "label": "Központi specialista",
        "keywords": ["specialista", "asszisztens", "elemző", "irodai", "központi"],
    },
}

MEDIA_QUERIES = [
    "Lidl béremelés fizetés kiskereskedelem",
    "ALDI béremelés fizetés kiskereskedelem",
    "SPAR béremelés fizetés kiskereskedelem",
    "Tesco béremelés fizetés kiskereskedelem",
    "PENNY béremelés fizetés kiskereskedelem",
    "Auchan béremelés fizetés kiskereskedelem",
    "Trade Magazin Lidl béremelés",
    "Trade Magazin Aldi béremelés",
    "Trade Magazin Tesco béremelés",
    "Trade Magazin Penny béremelés",
    "Trade Magazin Auchan béremelés",
    "Trade Magazin SPAR béremelés",
]

ALLOWED_MEDIA_DOMAINS = [
    "trademagazin.hu",
    "portfolio.hu",
    "penzcentrum.hu",
    "hrportal.hu",
    "24.hu",
    "hvg.hu",
    "vg.hu",
]

SALARY_PATTERNS = [
    r"bruttó\s+(\d{3,})\s*(?:ezer|000)?\s*(?:forint|ft)",
    r"(\d{3,})\s*ezer\s*(?:forint|ft)",
    r"(\d{3,})\s*000\s*(?:forint|ft)",
    r"(\d{1,3}(?:[\s\.]\d{3})+)\s*(?:forint|ft)",
]

RAISE_PATTERNS = [
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*százalékos\s+béremelés",
    r"béremelés[^\.]{0,80}?(\d{1,2}(?:[,.]\d{1,2})?)\s*százalék",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%-os\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*béremelés",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def clean_text(text):
    text = unescape(text or "")
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_hash(text):
    return hashlib.sha1(clean_text(text).lower().encode("utf-8")).hexdigest()[:16]


def fetch_url(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    try:
        request = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")

    except Exception as error:
        print(f"Fetch failed: {url} | {error}")
        return None


def google_news_rss(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={urllib.parse.quote_plus(query)}&hl=hu&gl=HU&ceid=HU:hu"
    )

    xml_text = fetch_url(url)
    time.sleep(REQUEST_DELAY_SECONDS)

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

            if not title and not description:
                continue

            combined = clean_text(f"{title}. {description}")

            if not is_allowed_media_text(combined, link):
                continue

            results.append({
                "title": title,
                "description": description,
                "link": link,
                "pub_date": pub_date,
                "combined": combined,
            })

    except Exception as error:
        print(f"RSS parse failed: {query} | {error}")

    return results


def is_allowed_media_text(text, link):
    lower = (text + " " + link).lower()

    return any(domain in lower for domain in ALLOWED_MEDIA_DOMAINS)


def detect_company(text):
    lower = text.lower()

    for company_id, company_name in COMPANIES.items():
        if company_id in lower or company_name.lower() in lower:
            return company_id

    return None


def detect_role(text):
    lower = text.lower()

    for role_key, config in ROLE_MAP.items():
        if any(keyword in lower for keyword in config["keywords"]):
            return role_key

    return None


def normalize_salary_value(raw):
    value = str(raw).replace(" ", "").replace(".", "").replace(",", ".")

    try:
        number = float(value)
    except ValueError:
        return None

    if number < 1000:
        number = number * 1000

    if number < 200000 or number > 2500000:
        return None

    return int(round(number))


def extract_salary_values(text):
    values = []

    for pattern in SALARY_PATTERNS:
        for match in re.findall(pattern, text.lower(), flags=re.I):
            value = normalize_salary_value(match)

            if value:
                values.append(value)

    return sorted(set(values))


def extract_raise_values(text):
    values = []

    for pattern in RAISE_PATTERNS:
        for match in re.findall(pattern, text.lower(), flags=re.I):
            try:
                value = float(str(match).replace(",", "."))
                if 1 <= value <= 40:
                    values.append(value)
            except ValueError:
                pass

    return sorted(set(values))


def extract_salary_from_posting(posting):
    text = clean_text(" ".join([
        str(posting.get("title", "")),
        str(posting.get("company", "")),
        str(posting.get("location", "")),
        str(posting.get("url", "")),
    ]))

    salary_min = posting.get("salary_min_huf")
    salary_max = posting.get("salary_max_huf")

    values = []

    if isinstance(salary_min, int):
        values.append(salary_min)

    if isinstance(salary_max, int):
        values.append(salary_max)

    values.extend(extract_salary_values(text))

    return sorted(set(values))


def source_confidence(source_type, sample_count, has_media_confirmation):
    base = 35

    if source_type == "static_salary_json":
        base = 45

    if source_type == "job_posting":
        base = 70

    if source_type == "business_media":
        base = 60

    base += min(sample_count, 10) * 3

    if has_media_confirmation:
        base += 10

    return max(0, min(95, base))


def build_baseline_records(salaries):
    records = []

    for row in salaries:
        company_id = row.get("id")
        company = row.get("company")

        if not company_id or not company:
            continue

        for role_key, config in ROLE_MAP.items():
            value = row.get(role_key)

            if not isinstance(value, int):
                continue

            records.append({
                "id": make_hash(f"{company_id}|{role_key}|baseline|{value}"),
                "company_id": company_id,
                "company": company,
                "role_key": role_key,
                "role_label": config["label"],
                "salary_min_huf_month": value,
                "salary_median_huf_month": value,
                "salary_max_huf_month": value,
                "salary_type": "gross_estimated",
                "source_type": "static_salary_json",
                "source_name": "salaries.json",
                "source_url": None,
                "confidence": 45,
                "evidence_text": row.get("notes", ""),
                "last_checked": now_iso(),
            })

    return records


def build_posting_records(postings):
    records = []

    for posting in postings:
        company_id = posting.get("company_id")
        company = posting.get("company")

        if company_id not in COMPANIES:
            continue

        role_key = detect_role(posting.get("title", ""))

        if not role_key:
            continue

        values = extract_salary_from_posting(posting)

        if not values:
            continue

        min_value = min(values)
        max_value = max(values)
        median_value = round((min_value + max_value) / 2)

        records.append({
            "id": make_hash(f"{company_id}|{role_key}|posting|{posting.get('posting_id')}"),
            "company_id": company_id,
            "company": company,
            "role_key": role_key,
            "role_label": ROLE_MAP[role_key]["label"],
            "salary_min_huf_month": min_value,
            "salary_median_huf_month": median_value,
            "salary_max_huf_month": max_value,
            "salary_type": "gross_visible_or_parsed",
            "source_type": "job_posting",
            "source_name": posting.get("source", "job_posting"),
            "source_url": posting.get("url"),
            "confidence": 75,
            "evidence_text": posting.get("title", ""),
            "last_checked": now_iso(),
        })

    return records


def build_media_records():
    records = []

    seen = set()

    for query in MEDIA_QUERIES:
        print(f"Media query: {query}")

        for result in google_news_rss(query):
            text = clean_text(result.get("combined", ""))
            link = result.get("link", "")

            key = make_hash(text + link)

            if key in seen:
                continue

            seen.add(key)

            company_id = detect_company(text)

            if not company_id:
                continue

            salary_values = extract_salary_values(text)
            raise_values = extract_raise_values(text)

            if not salary_values and not raise_values:
                continue

            role_key = detect_role(text)

            record_type = "salary_level" if salary_values else "salary_raise_signal"

            records.append({
                "id": make_hash(f"{company_id}|media|{link}|{text}"),
                "company_id": company_id,
                "company": COMPANIES[company_id],
                "role_key": role_key,
                "role_label": ROLE_MAP[role_key]["label"] if role_key else "Általános vállalati bérinformáció",
                "record_type": record_type,
                "salary_min_huf_month": min(salary_values) if salary_values else None,
                "salary_median_huf_month": round(sum(salary_values) / len(salary_values)) if salary_values else None,
                "salary_max_huf_month": max(salary_values) if salary_values else None,
                "raise_pct": max(raise_values) if raise_values else None,
                "salary_type": "gross_or_unspecified_media_report",
                "source_type": "business_media",
                "source_name": detect_media_source(text, link),
                "source_url": link,
                "confidence": 60 if salary_values else 55,
                "evidence_text": text[:500],
                "last_checked": now_iso(),
            })

    return records


def detect_media_source(text, link):
    lower = (text + " " + link).lower()

    for domain in ALLOWED_MEDIA_DOMAINS:
        if domain in lower:
            return domain

    return "business_media"


def median(values):
    values = sorted(values)

    if not values:
        return None

    mid = len(values) // 2

    if len(values) % 2 == 1:
        return values[mid]

    return round((values[mid - 1] + values[mid]) / 2)


def aggregate_role(company_id, company, role_key, records):
    relevant = [
        r for r in records
        if r.get("company_id") == company_id
        and r.get("role_key") == role_key
        and isinstance(r.get("salary_median_huf_month"), int)
    ]

    baseline = [
        r for r in relevant
        if r.get("source_type") == "static_salary_json"
    ]

    non_baseline = [
        r for r in relevant
        if r.get("source_type") != "static_salary_json"
    ]

    preferred = non_baseline if non_baseline else baseline

    values = [
        r["salary_median_huf_month"]
        for r in preferred
    ]

    if not values:
        return None

    samples = len(preferred)
    media_confirmation = any(r.get("source_type") == "business_media" for r in relevant)

    confidence = source_confidence(
        "job_posting" if non_baseline else "static_salary_json",
        samples,
        media_confirmation,
    )

    return {
        "role_key": role_key,
        "role_label": ROLE_MAP[role_key]["label"],
        "salary_min_huf_month": min(values),
        "salary_median_huf_month": median(values),
        "salary_max_huf_month": max(values),
        "sample_count": samples,
        "confidence": confidence,
        "source_mix": summarize_source_mix(preferred),
    }


def summarize_source_mix(records):
    counts = {}

    for record in records:
        source = record.get("source_type", "unknown")
        counts[source] = counts.get(source, 0) + 1

    return [
        {
            "source_type": source,
            "count": count,
        }
        for source, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def aggregate_company(company_id, records):
    company = COMPANIES[company_id]
    roles = []

    for role_key in ROLE_MAP.keys():
        item = aggregate_role(company_id, company, role_key, records)
        if item:
            roles.append(item)

    company_records = [
        r for r in records
        if r.get("company_id") == company_id
    ]

    raise_signals = [
        r for r in company_records
        if r.get("record_type") == "salary_raise_signal"
    ]

    visible_salary_records = [
        r for r in company_records
        if r.get("source_type") in ["job_posting", "business_media"]
        and isinstance(r.get("salary_median_huf_month"), int)
    ]

    avg_confidence = (
        round(sum(role["confidence"] for role in roles) / len(roles))
        if roles else 0
    )

    return {
        "company_id": company_id,
        "company": company,
        "roles": roles,
        "salary_raise_signals": raise_signals[:5],
        "visible_salary_records_count": len(visible_salary_records),
        "total_salary_records_count": len(company_records),
        "average_confidence": avg_confidence,
        "salary_data_status": (
            "partly_validated"
            if visible_salary_records
            else "baseline_estimate_only"
        ),
    }


def build_output():
    salaries = load_json(SALARIES_FILE, [])
    postings = load_json(POSTINGS_FILE, [])

    baseline_records = build_baseline_records(salaries)
    posting_records = build_posting_records(postings)
    media_records = build_media_records()

    all_records = baseline_records + posting_records + media_records

    companies = [
        aggregate_company(company_id, all_records)
        for company_id in COMPANIES.keys()
    ]

    return {
        "updated_at": now_iso(),
        "status": "ok",
        "source_files": [
            "docs/data/salaries.json",
            "docs/data/job-postings-current.json",
        ],
        "method": "salary_intelligence_v1_static_baseline_posting_media_control",
        "important_note": (
            "Ez a fájl nem hivatalos bérstatisztika. "
            "A salaries.json becsléseit, az álláshirdetésekből kinyerhető béradatokat "
            "és a szakmai/üzleti médiában megjelenő bérinformációkat kapcsolja össze. "
            "Ahol nincs álláshirdetésből vagy médiából megerősített bérszám, ott az érték baseline becslés."
        ),
        "companies": companies,
        "records": all_records,
    }


def main():
    print("Salary Intelligence updater started.")

    output = build_output()

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Records: {len(output.get('records', []))}")


if __name__ == "__main__":
    main()
