#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FMCG Salary Raw Data Collector v2

Cél:
- 6 FMCG szereplő bérinformációinak begyűjtése.
- Csak nyers adatgyűjtés.
- Nem számol indexet.
- Nem módosítja a salaries.json fájlt.
- Javított bérfelismerés:
  - 587 ezer
  - 674 ezres
  - bruttó 595 200 forint
  - 1 millió
  - millió körüli
  - 620-680 ezer
  - 6-8 százalékos béremelés

Kimenet:
docs/data/salary-raw-data.json
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
OUTPUT_FILE = DATA_DIR / "salary-raw-data.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/125 Safari/537.36"
)

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 2


COMPANIES = {
    "lidl": ["Lidl", "Lidl Magyarország"],
    "aldi": ["ALDI", "Aldi", "ALDI Magyarország"],
    "spar": ["SPAR", "Spar", "SPAR Magyarország"],
    "tesco": ["Tesco", "Tesco Magyarország"],
    "penny": ["PENNY", "Penny", "Penny Market"],
    "auchan": ["Auchan", "Auchan Magyarország"],
}


ROLE_KEYWORDS = {
    "cashier": ["pénztáros", "kasszás", "eladó-pénztáros", "eladó pénztáros"],
    "stocker": ["árufeltöltő", "bolti dolgozó", "bolti munkatárs", "eladó", "áruházi dolgozó"],
    "bakery_worker": ["pék", "pékáru", "pékség"],
    "shift_leader": ["műszakvezető", "műszak vezető", "shift leader"],
    "department_manager": ["osztályvezető", "részlegvezető", "csoportvezető"],
    "store_manager": ["üzletvezető", "áruházvezető", "boltvezető", "store manager"],
    "warehouse_worker": ["raktári dolgozó", "raktáros", "targoncavezető", "komissiózó"],
    "office_specialist": ["specialista", "asszisztens", "elemző", "irodai", "központi"],
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
        f'{main_name} fizetés',
        f'{main_name} bér',
        f'{main_name} béremelés',
        f'{main_name} bruttó fizetés',
        f'{main_name} bruttó bér',
        f'{main_name} pénztáros fizetés',
        f'{main_name} árufeltöltő fizetés',
        f'{main_name} áruházi dolgozó fizetés',
        f'{main_name} raktári dolgozó fizetés',
        f'{main_name} üzletvezető fizetés',
        f'{main_name} bolti dolgozó bér',
        f'{main_name} Trade Magazin béremelés',
        f'{main_name} Portfolio béremelés',
        f'{main_name} Pénzcentrum fizetés',
        f'{main_name} HR Portal béremelés',
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
    r"(\d{3,4})\s*[-–]\s*(\d{3,4})\s*ezres",
    r"(\d+[,.]?\d*)\s*[-–]\s*(\d+[,.]?\d*)\s*millió\s*(?:forint|ft)?",
    r"(\d+[,.]?\d*)\s*és\s*(\d+[,.]?\d*)\s*millió\s*(?:forint|ft)?",
    r"bruttó\s+(\d{3,4})\s*[-–]\s*(\d{3,4})\s*ezer",
]


RAISE_PATTERNS = [
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*százalékos\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%-os\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*béremelés",
    r"béremelés[^\.]{0,120}?(\d{1,2}(?:[,.]\d{1,2})?)\s*százalék",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*[-–]\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*százalékos\s+béremelés",
    r"(\d{1,2}(?:[,.]\d{1,2})?)\s*[-–]\s*(\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*béremelés",
]


BAD_SALARY_CONTEXT = [
    "milliárd",
    "milliárdot",
    "mrd",
    "forgalom",
    "árbevétel",
    "bevétel",
    "beruházás",
    "négyzetméter",
    "üzlet",
    "áruházat épít",
    "bírság",
    "adó",
    "profit",
    "nyereség",
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

            combined = clean_text(f"{title}. {description}")

            if not combined:
                continue

            if not allowed_source(combined, link):
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


def detect_company(text):
    lower = text.lower()

    for company_id, aliases in COMPANIES.items():
        for alias in aliases:
            if alias.lower() in lower:
                return company_id

    return None


def detect_role(text):
    lower = text.lower()

    for role_key, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lower:
                return role_key

    return None


def normalize_money(value):
    value = str(value).lower().strip()

    if value in ["egymilliós", "millió körüli"]:
        return 1000000

    value = value.replace(" ", "")
    value = value.replace(".", "")
    value = value.replace(",", ".")

    try:
        number = float(value)
    except ValueError:
        return None

    if 0.5 <= number <= 3:
        number *= 1000000
    elif 100 <= number <= 3000:
        number *= 1000

    if number < 200000:
        return None

    if number > 3000000:
        return None

    return int(round(number))


def has_bad_salary_context(text):
    lower = text.lower()

    if "fizetés" in lower or "bér" in lower or "bruttó" in lower or "nettó" in lower or "keres" in lower:
        return False

    return any(term in lower for term in BAD_SALARY_CONTEXT)


def extract_salary_values(text):
    text = clean_text(text)
    values = []

    if has_bad_salary_context(text):
        return []

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


def extract_salary_ranges(text):
    text = clean_text(text)
    ranges = []

    if has_bad_salary_context(text):
        return []

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
                    "salary_max_huf_month": high,
                    "salary_median_huf_month": round((low + high) / 2),
                })

    return ranges


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


def confidence_for_record(record_type, role_key, text):
    confidence = 50
    lower = text.lower()

    if record_type == "salary_range":
        confidence += 20

    if record_type == "salary":
        confidence += 15

    if record_type == "raise":
        confidence += 10

    if role_key:
        confidence += 10

    if "bruttó" in lower:
        confidence += 10

    if "nettó" in lower:
        confidence += 6

    if "havi" in lower or "hó" in lower:
        confidence += 5

    if "béremelés" in lower:
        confidence += 5

    if "áruházi dolgozó" in lower or "üzletvezető" in lower or "pénztáros" in lower:
        confidence += 5

    return min(confidence, 95)


def build_salary_record(company_id, role_key, value, result):
    company_name = COMPANIES[company_id][0]
    text = clean_text(result.get("combined", ""))

    return {
        "id": make_hash(f"{company_id}|{role_key}|salary|{value}|{result.get('link')}"),
        "company_id": company_id,
        "company": company_name,
        "role_key": role_key,
        "value_type": "salary_huf_month",
        "salary_min_huf_month": value,
        "salary_median_huf_month": value,
        "salary_max_huf_month": value,
        "raise_pct": None,
        "source_name": detect_source_name(text, result.get("link", "")),
        "source_url": result.get("link", ""),
        "published_or_found_date": result.get("pub_date", ""),
        "evidence_text": text[:600],
        "confidence": confidence_for_record("salary", role_key, text),
        "collected_at": now_iso(),
    }


def build_salary_range_record(company_id, role_key, salary_range, result):
    company_name = COMPANIES[company_id][0]
    text = clean_text(result.get("combined", ""))

    return {
        "id": make_hash(f"{company_id}|{role_key}|range|{salary_range}|{result.get('link')}"),
        "company_id": company_id,
        "company": company_name,
        "role_key": role_key,
        "value_type": "salary_range_huf_month",
        "salary_min_huf_month": salary_range["salary_min_huf_month"],
        "salary_median_huf_month": salary_range["salary_median_huf_month"],
        "salary_max_huf_month": salary_range["salary_max_huf_month"],
        "raise_pct": None,
        "source_name": detect_source_name(text, result.get("link", "")),
        "source_url": result.get("link", ""),
        "published_or_found_date": result.get("pub_date", ""),
        "evidence_text": text[:600],
        "confidence": confidence_for_record("salary_range", role_key, text),
        "collected_at": now_iso(),
    }


def build_raise_record(company_id, value, result):
    company_name = COMPANIES[company_id][0]
    text = clean_text(result.get("combined", ""))

    return {
        "id": make_hash(f"{company_id}|raise|{value}|{result.get('link')}"),
        "company_id": company_id,
        "company": company_name,
        "role_key": None,
        "value_type": "salary_raise_pct",
        "salary_min_huf_month": None,
        "salary_median_huf_month": None,
        "salary_max_huf_month": None,
        "raise_pct": value,
        "source_name": detect_source_name(text, result.get("link", "")),
        "source_url": result.get("link", ""),
        "published_or_found_date": result.get("pub_date", ""),
        "evidence_text": text[:600],
        "confidence": confidence_for_record("raise", None, text),
        "collected_at": now_iso(),
    }


def deduplicate(records):
    seen = set()
    result = []

    for record in records:
        key = record.get("id")

        if key in seen:
            continue

        seen.add(key)
        result.append(record)

    return result


def summarize(records):
    companies = []

    for company_id, aliases in COMPANIES.items():
        company_records = [
            item for item in records
            if item.get("company_id") == company_id
        ]

        salary_records = [
            item for item in company_records
            if item.get("value_type") in ["salary_huf_month", "salary_range_huf_month"]
        ]

        raise_records = [
            item for item in company_records
            if item.get("value_type") == "salary_raise_pct"
        ]

        roles_found = sorted(set(
            item.get("role_key") for item in salary_records
            if item.get("role_key")
        ))

        companies.append({
            "company_id": company_id,
            "company": aliases[0],
            "records_count": len(company_records),
            "salary_records_count": len(salary_records),
            "raise_records_count": len(raise_records),
            "roles_found": roles_found,
            "average_confidence": round(
                sum(item.get("confidence", 0) for item in company_records) / len(company_records)
            ) if company_records else 0,
            "sample_records": company_records[:5],
        })

    return companies


def collect_records():
    records = []
    raw_results = []

    for query in SEARCH_QUERIES:
        print(f"Query: {query}")

        results = google_news_rss(query)

        for result in results:
            text = result.get("combined", "")
            company_id = detect_company(text)

            if not company_id:
                continue

            role_key = detect_role(text)
            salary_values = extract_salary_values(text)
            salary_ranges = extract_salary_ranges(text)
            raise_values = extract_raise_values(text)

            for salary_range in salary_ranges:
                records.append(
                    build_salary_range_record(
                        company_id=company_id,
                        role_key=role_key,
                        salary_range=salary_range,
                        result=result,
                    )
                )

            for value in salary_values:
                records.append(
                    build_salary_record(
                        company_id=company_id,
                        role_key=role_key,
                        value=value,
                        result=result,
                    )
                )

            for value in raise_values:
                records.append(
                    build_raise_record(
                        company_id=company_id,
                        value=value,
                        result=result,
                    )
                )

            raw_results.append({
                "query": query,
                "company_id": company_id,
                "role_key": role_key,
                "salary_values": salary_values,
                "salary_ranges": salary_ranges,
                "raise_values": raise_values,
                "source_url": result.get("link", ""),
                "text": text[:600],
            })

    records = deduplicate(records)

    return records, raw_results


def build_output():
    records, raw_results = collect_records()

    return {
        "updated_at": now_iso(),
        "status": "ok" if records else "no_salary_records_found",
        "method": "salary_raw_data_v2_google_news_rss_targeted_queries_improved_salary_parser",
        "important_note": (
            "Ez nyers OSINT béradat-gyűjtés. Csak konkrét bérszámokat, bérsávokat "
            "és béremelési százalékokat ment. Nem hivatalos bérstatisztika, "
            "nem módosítja a salaries.json fájlt."
        ),
        "companies": summarize(records),
        "records": records,
        "raw_results": raw_results[:150],
    }


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main():
    print("Salary Raw Data Collector v2 started.")

    output = build_output()

    save_json(OUTPUT_FILE, output)

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Status: {output['status']}")
    print(f"Records: {len(output.get('records', []))}")


if __name__ == "__main__":
    main()
