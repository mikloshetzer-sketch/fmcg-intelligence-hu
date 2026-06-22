#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Intelligence v6 - RAW DATA COLLECTOR

Kimenet:
- docs/data/salary-raw-data.json

Fontos:
- Ez a script CSAK nyers béradatot gyűjt.
- A salary-summary.json és salary-role-summary.json fájlokat
  külön script készíti: scripts/update_salary_summary.py
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
from email.utils import parsedate_to_datetime
from html import unescape


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

RAW_OUTPUT_FILE = DATA_DIR / "salary-raw-data.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/125 Safari/537.36"
)

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 2
MIN_YEAR = 2024


COMPANIES = {
    "lidl": ["Lidl", "Lidl Magyarország"],
    "aldi": ["ALDI", "Aldi", "ALDI Magyarország"],
    "spar": ["SPAR", "Spar", "SPAR Magyarország"],
    "tesco": ["Tesco", "Tesco Magyarország"],
    "penny": ["PENNY", "Penny", "Penny Market"],
    "auchan": ["Auchan", "Auchan Magyarország"],
}


ROLE_KEYWORDS = {
    "cashier": ["pénztáros", "kasszás", "kassza", "eladó-pénztáros", "eladó pénztáros"],
    "stocker": [
        "árufeltöltő", "áruházi dolgozó", "áruházi munkatárs",
        "bolti dolgozó", "bolti munkatárs", "fizikai munkát végző",
        "fizikai munkát végzők", "új munkatárs", "dolgozókat",
        "áruházi munkavállaló", "bolti eladó", "bolti munkavállaló"
    ],
    "bakery_worker": ["pék", "pékáru", "pékség"],
    "shift_leader": ["műszakvezető", "műszak vezető", "shift leader"],
    "department_manager": ["osztályvezető", "részlegvezető", "csoportvezető", "területi vezető"],
    "store_manager": ["üzletvezető", "áruházvezető", "boltvezető", "store manager", "vezetőket"],
    "warehouse_worker": ["raktári dolgozó", "raktáros", "targoncavezető", "komissiózó", "logisztikai dolgozó"],
    "office_specialist": ["specialista", "asszisztens", "elemző", "irodai", "központi", "beszerzés"],
}


ALLOWED_DOMAINS = [
    "trademagazin.hu",
    "portfolio.hu",
    "penzcentrum.hu",
    "hrportal.hu",
    "24.hu",
    "hvg.hu",
    "vg.hu",
    "profession.hu",
    "jobinfo.hu",
    "indeed.com",
    "hu.indeed.com",
]


SEARCH_QUERIES = []

for company_id, aliases in COMPANIES.items():
    main_name = aliases[0]

    SEARCH_QUERIES.extend([
        f'{main_name} dolgozói béremelés',
        f'{main_name} munkavállalói bér',
        f'{main_name} bruttó bér',
        f'{main_name} bruttó alapbér',
        f'{main_name} alapbér',
        f'{main_name} dolgozók alapbére',
        f'{main_name} dolgozói fizetés',
        f'{main_name} mennyit keresnek a dolgozók',
        f'{main_name} kereshetnek a dolgozók',
        f'{main_name} áruházi dolgozó bér',
        f'{main_name} bolti dolgozó bér',
        f'{main_name} pénztáros bére',
        f'{main_name} árufeltöltő bére',
        f'{main_name} raktári dolgozó bére',
        f'{main_name} üzletvezető bére',
        f'{main_name} Portfolio béremelés',
        f'{main_name} HVG bér',
        f'{main_name} 24.hu béremelés',
        f'{main_name} Pénzcentrum bér',
        f'{main_name} Trade Magazin béremelés',
    ])


SALARY_PATTERNS = [
    r"bruttó\s+havi\s+(\d{1,3}(?:[\s\.]\d{3})+|\d{3,4})\s*(?:forint|ft)?",
    r"bruttó\s+(\d{1,3}(?:[\s\.]\d{3})+|\d{3,4})\s*(?:forint|ft)?",
    r"nettó\s+(\d{1,3}(?:[\s\.]\d{3})+|\d{3,4})\s*(?:forint|ft)?",
    r"(\d{1,3}(?:[\s\.]\d{3})+)\s*(?:forint|ft)",
    r"(\d{3,4})\s*000\s*(?:forint|ft)",
    r"(\d{3,4})\s*ezer\s*(?:forint|ft)?",
    r"(\d{3,4})\s*ezres",
    r"(\d+[,.]?\d*)\s*millió\s*(?:forint|ft)?",
    r"(\d+[,.]?\d*)\s*milliós",
    r"egymilliós",
    r"millió\s+körüli",
]


SALARY_RANGE_PATTERNS = [
    r"(\d{3,4})\s*[-–]\s*(\d{3,4})\s*ezer\s*(?:forint|ft)?",
    r"(\d{3,4})\s*ezer[^\.]{0,140}?(\d{3,4})\s*ezerig",
    r"(\d{3,4})\s*ezerért[^\.]{0,140}?(\d{3,4})\s*ezerig",
    r"bruttó\s+(\d{3,4})\s*ezer[^\.]{0,140}?(\d{3,4})\s*ezerig",
    r"(\d{3,4})\s*ezer[^\.]{0,140}?felcsúszhat\s+(\d{3,4})\s*ezerig",
]


RAISE_PATTERNS = [
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*százalékos\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%-os\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*béremelés",
    r"béremelés[^\.]{0,140}?(\d{1,2}(?:[,.]\d{1,2})?)\s*százalék",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*[-–]\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*százalékos\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*[-–]\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*béremelés",
]


BAD_CONTEXT = [
    "milliárd", "milliárdot", "mrd", "árbevétel", "bevétel",
    "beruházás", "négyzetméter", "bírság", "adó", "profit", "nyereség",
    "fizetési megoldás", "fizetési mód", "bankkártya", "mobilfizetés"
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    }

    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
            body = response.read().decode(charset, errors="ignore")
            return body, final_url
    except Exception as error:
        print(f"Fetch failed: {url} | {error}")
        return None, url


def google_news_rss(query):
    url = (
        "https://news.google.com/rss/search?"
        f"q={urllib.parse.quote_plus(query)}&hl=hu&gl=HU&ceid=HU:hu"
    )

    xml_text, _ = fetch_url(url)
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

            combined = clean_text(f"{title}. {description}")

            if not combined:
                continue

            if not is_recent_enough(pub_date, combined):
                continue

            if not allowed_source(combined, link):
                continue

            if is_bad_context(combined):
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


def allowed_source(text, link):
    lower = (text + " " + link).lower()
    return any(domain in lower for domain in ALLOWED_DOMAINS)


def is_recent_enough(pub_date, text):
    try:
        if pub_date:
            dt = parsedate_to_datetime(pub_date)
            return dt.year >= MIN_YEAR
    except Exception:
        pass

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    return max(years) >= MIN_YEAR if years else True


def is_bad_context(text):
    lower = text.lower()
    return any(item in lower for item in BAD_CONTEXT)


def detect_company(text):
    lower = text.lower()

    for company_id, aliases in COMPANIES.items():
        for alias in aliases:
            if alias.lower() in lower:
                return company_id

    return None


def detect_role(text):
    lower = text.lower()
    scores = {}

    for role_key, keywords in ROLE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lower)
        if score:
            scores[role_key] = score

    if not scores:
        return None

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[0][0]


def normalize_money(value):
    value = str(value).lower().strip()

    if value in ["egymilliós", "millió körüli"]:
        return 1000000

    value = value.replace(" ", "").replace(".", "").replace(",", ".")

    try:
        number = float(value)
    except ValueError:
        return None

    if 0.5 <= number <= 3:
        number *= 1000000
    elif 100 <= number <= 3000:
        number *= 1000

    if 200000 <= number <= 3000000:
        return int(round(number))

    return None


def salary_context_ok(text):
    lower = text.lower()

    positive_terms = [
        "fizetés", "fizetése", "bér", "bérek", "bruttó", "nettó",
        "keres", "kereshet", "alapbér", "dolgozó", "munkavállaló",
        "béremelés", "juttatás"
    ]

    return any(term in lower for term in positive_terms) and not is_bad_context(text)


def extract_salary_ranges(text):
    text = clean_text(text)

    if not salary_context_ok(text):
        return []

    ranges = []

    for pattern in SALARY_RANGE_PATTERNS:
        for match in re.findall(pattern, text.lower(), flags=re.I):
            if not isinstance(match, tuple) or len(match) != 2:
                continue

            low = normalize_money(match[0])
            high = normalize_money(match[1])

            if low and high:
                if low > high:
                    low, high = high, low

                ranges.append({
                    "salary_min_huf_month": low,
                    "salary_median_huf_month": round((low + high) / 2),
                    "salary_max_huf_month": high,
                })

    seen = set()
    output = []

    for item in ranges:
        key = (item["salary_min_huf_month"], item["salary_max_huf_month"])
        if key not in seen:
            seen.add(key)
            output.append(item)

    return output


def extract_salary_values(text):
    text = clean_text(text)

    if not salary_context_ok(text):
        return []

    values = []

    for pattern in SALARY_PATTERNS:
        if pattern in ["egymilliós", "millió\\s+körüli"]:
            continue

        for match in re.findall(pattern, text.lower(), flags=re.I):
            if isinstance(match, tuple):
                continue

            value = normalize_money(match)
            if value:
                values.append(value)

    lower = text.lower()

    if "egymilliós" in lower:
        values.append(1000000)

    if "millió körüli" in lower:
        values.append(1000000)

    return sorted(set(values))


def extract_raise_values(text):
    values = []

    for pattern in RAISE_PATTERNS:
        for match in re.findall(pattern, text.lower(), flags=re.I):
            if isinstance(match, tuple):
                nums = []
                for part in match:
                    try:
                        value = float(str(part).replace(",", "."))
                        if 1 <= value <= 50:
                            nums.append(value)
                    except ValueError:
                        pass
                if nums:
                    values.append(max(nums))
                continue

            try:
                value = float(str(match).replace(",", "."))
                if 1 <= value <= 50:
                    values.append(value)
            except ValueError:
                pass

    return sorted(set(values))


def detect_source_name(text, link):
    lower = (text + " " + link).lower()

    for domain in ALLOWED_DOMAINS:
        if domain in lower:
            return domain

    return "unknown"


def confidence_for_record(record_type, role_key, text, source_count=1):
    lower = text.lower()
    confidence = 50

    if record_type == "salary_range":
        confidence += 20
    elif record_type == "salary":
        confidence += 15
    elif record_type == "raise":
        confidence += 10

    if role_key:
        confidence += 10

    if "bruttó" in lower:
        confidence += 10

    if "alapbér" in lower:
        confidence += 5

    if "havi" in lower or "hó" in lower:
        confidence += 5

    confidence += min(10, max(0, source_count - 1) * 2)

    return min(confidence, 95)


def build_record(company_id, role_key, value_type, result, text, salary_range=None, salary_value=None, raise_pct=None):
    company_name = COMPANIES[company_id][0]
    source_name = detect_source_name(text, result.get("link", ""))

    if salary_range:
        salary_min = salary_range["salary_min_huf_month"]
        salary_median = salary_range["salary_median_huf_month"]
        salary_max = salary_range["salary_max_huf_month"]
    elif salary_value:
        salary_min = salary_value
        salary_median = salary_value
        salary_max = salary_value
    else:
        salary_min = None
        salary_median = None
        salary_max = None

    return {
        "id": make_hash(f"{company_id}|{role_key}|{value_type}|{salary_min}|{salary_max}|{raise_pct}|{result.get('link')}"),
        "company_id": company_id,
        "company": company_name,
        "role_key": role_key,
        "value_type": value_type,
        "salary_min_huf_month": salary_min,
        "salary_median_huf_month": salary_median,
        "salary_max_huf_month": salary_max,
        "raise_pct": raise_pct,
        "source_name": source_name,
        "source_url": result.get("link", ""),
        "google_news_url": result.get("link", ""),
        "published_or_found_date": result.get("pub_date", ""),
        "evidence_text": text[:900],
        "confidence": confidence_for_record(
            "salary_range" if value_type == "salary_range_huf_month"
            else "raise" if value_type == "salary_raise_pct"
            else "salary",
            role_key,
            text,
        ),
        "collected_at": now_iso(),
    }


def merge_duplicate_records(records):
    grouped = {}

    for record in records:
        key = (
            record.get("company_id"),
            record.get("role_key"),
            record.get("value_type"),
            record.get("salary_min_huf_month"),
            record.get("salary_max_huf_month"),
            record.get("raise_pct"),
        )

        if key not in grouped:
            record["source_count"] = 1
            record["source_urls"] = [record.get("source_url")]
            record["source_names"] = [record.get("source_name")]
            grouped[key] = record
            continue

        existing = grouped[key]
        existing["source_count"] += 1

        if record.get("source_url") not in existing["source_urls"]:
            existing["source_urls"].append(record.get("source_url"))

        if record.get("source_name") not in existing["source_names"]:
            existing["source_names"].append(record.get("source_name"))

        existing["confidence"] = max(existing["confidence"], record["confidence"])

    output = list(grouped.values())

    for item in output:
        item["confidence"] = confidence_for_record(
            "salary_range" if item["value_type"] == "salary_range_huf_month"
            else "raise" if item["value_type"] == "salary_raise_pct"
            else "salary",
            item.get("role_key"),
            item.get("evidence_text", ""),
            item.get("source_count", 1),
        )

    return output


def summarize_raw(records):
    companies = []

    for company_id, aliases in COMPANIES.items():
        company_records = [r for r in records if r["company_id"] == company_id]
        salary_records = [r for r in company_records if r["value_type"] in ["salary_huf_month", "salary_range_huf_month"]]
        raise_records = [r for r in company_records if r["value_type"] == "salary_raise_pct"]

        companies.append({
            "company_id": company_id,
            "company": aliases[0],
            "records_count": len(company_records),
            "salary_records_count": len(salary_records),
            "raise_records_count": len(raise_records),
            "roles_found": sorted(set(r["role_key"] for r in salary_records if r.get("role_key"))),
            "average_confidence": round(sum(r["confidence"] for r in company_records) / len(company_records)) if company_records else 0,
            "sample_records": company_records[:5],
        })

    return companies


def collect_records():
    records = []
    raw_results = []
    seen_raw = set()

    for query in SEARCH_QUERIES:
        print(f"Query: {query}")

        for result in google_news_rss(query):
            raw_key = make_hash(result["combined"] + result["link"])

            if raw_key in seen_raw:
                continue

            seen_raw.add(raw_key)

            text = result["combined"]

            if is_bad_context(text):
                continue

            company_id = detect_company(text)

            if not company_id:
                continue

            role_key = detect_role(text)
            salary_ranges = extract_salary_ranges(text)
            salary_values = [] if salary_ranges else extract_salary_values(text)
            raise_values = extract_raise_values(text)

            for salary_range in salary_ranges:
                records.append(build_record(
                    company_id, role_key, "salary_range_huf_month",
                    result, text, salary_range=salary_range
                ))

            for salary_value in salary_values:
                records.append(build_record(
                    company_id, role_key, "salary_huf_month",
                    result, text, salary_value=salary_value
                ))

            for raise_value in raise_values:
                records.append(build_record(
                    company_id, None, "salary_raise_pct",
                    result, text, raise_pct=raise_value
                ))

            raw_results.append({
                "query": query,
                "company_id": company_id,
                "role_key": role_key,
                "salary_values": salary_values,
                "salary_ranges": salary_ranges,
                "raise_values": raise_values,
                "source_url": result["link"],
                "published_or_found_date": result["pub_date"],
                "text": text[:900],
            })

    records = merge_duplicate_records(records)

    records = sorted(
        records,
        key=lambda r: (
            r["company_id"],
            r.get("role_key") or "",
            r["value_type"],
            -(r.get("confidence") or 0),
        )
    )

    return records, raw_results


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main():
    print("Salary Intelligence v6 started.")

    records, raw_results = collect_records()

    raw_output = {
        "updated_at": now_iso(),
        "status": "ok" if records else "no_salary_records_found",
        "method": "salary_raw_data_v6_clean_queries",
        "min_year": MIN_YEAR,
        "important_note": (
            "Ez nyers OSINT béradat-gyűjtés. "
            "Csak konkrét bérszámokat, bérsávokat "
            "és béremelési százalékokat ment. "
            "A salary-summary.json és salary-role-summary.json fájlokat "
            "külön script készíti."
        ),
        "companies": summarize_raw(records),
        "records": records,
        "raw_results": raw_results[:150],
    }

    save_json(RAW_OUTPUT_FILE, raw_output)

    print(f"Saved: {RAW_OUTPUT_FILE}")
    print(f"Records: {len(records)}")


if __name__ == "__main__":
    main()
