import json
import re
import time
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from html import unescape


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
HISTORY_DIR = DATA_DIR / "jobs-history"
RAW_DIR = DATA_DIR / "jobs-raw"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

SOURCES_FILE = DATA_DIR / "job-sources.json"
JOBS_FILE = DATA_DIR / "jobs.json"
CURRENT_POSTINGS_FILE = DATA_DIR / "job-postings-current.json"
STATUS_FILE = DATA_DIR / "jobs-monitor-status.json"

USER_AGENT = "Mozilla/5.0 (compatible; FMCG-Intelligence-Hungary/1.0)"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 2


FMCG_JOB_TERMS = [
    "eladó", "pénztáros", "kasszás", "árufeltöltő",
    "bolti munkatárs", "boltimunkatárs", "áruházi munkatárs",
    "kereskedelmi munkatárs",

    "hentes", "húspult", "sajtpult", "halpult",
    "csemegepult", "csemegepult eladó", "csemegepultos",
    "frissáru", "frissáru eladó", "zöldség", "zöldség-gyümölcs",
    "pék", "cukrász", "pékcsomagoló",

    "raktár", "raktári dolgozó", "raktáros", "komissiózó",
    "pikker", "targoncavezető", "árufogadó", "áruátvevő",
    "árukiadó", "logisztikai ügyintéző",

    "higiénikus", "higiéniai munkatárs",
    "műszaki eladó",

    "üzletvezető", "üzletvezető-helyettes",
    "boltvezető", "boltvezető-helyettes",
    "áruházvezető", "műszakvezető", "részlegvezető",
    "osztályvezető", "területi vezető", "régióvezető",
    "manager", "menedzser", "team leader",

    "beszerző", "kontroller", "elemző", "specialista",
    "asszisztens", "hr munkatárs", "bér-tb"
]


COMPANY_ALIASES = {
    "lidl": ["lidl"],
    "aldi": ["aldi"],
    "spar": ["spar", "interspar"],
    "tesco": ["tesco", "tesco-bst"],
    "penny": ["penny", "penny-market", "penny market"],
    "auchan": ["auchan"]
}


BAD_TERMS = [
    "cookie", "süti", "adatvédelem", "adatkezelés", "impresszum",
    "kapcsolat", "rendezvényeink", "történetünk", "értékeink",
    "juttatásaink", "díjaink", "karrier nálunk", "kiválasztási folyamat",
    "jelentkezési folyamat", "betanulás", "pályázatodhoz",
    "munkáltató", "életkörülménye", "felhasználási feltételek",
    "hírlevél", "social media", "facebook", "linkedin", "youtube",
    "instagram", "megnézem az állást", "részletek elrejtése",
    "előresorolva", "állás dátuma", "főbb feladatok", "nem kell nyelvtudás",
    "magyar középfok", "angol középfok", "feladva május", "feladva június",
    "dinamikusan fejlődő csapatába", "munkatársak szakmai képzésének"
]


CATEGORY_KEYWORDS = {
    "store": [
        "eladó", "pénztáros", "kasszás", "árufeltöltő",
        "bolti", "boltimunkatárs", "áruházi munkatárs",
        "kereskedelmi munkatárs", "hentes", "húspult", "sajtpult",
        "halpult", "csemegepult", "csemegepultos", "frissáru",
        "zöldség", "pék", "cukrász", "pékcsomagoló",
        "higiénikus", "higiéniai munkatárs", "műszaki eladó"
    ],
    "warehouse": [
        "raktár", "raktári", "raktáros", "komissiózó", "pikker",
        "targoncavezető", "árufogadó", "áruátvevő", "árukiadó",
        "logisztikai ügyintéző"
    ],
    "office": [
        "iroda", "központ", "beszerző", "kontroller", "marketing",
        "hr", "pénzügy", "it", "elemző", "specialista", "asszisztens",
        "bér-tb"
    ],
    "management": [
        "üzletvezető", "üzletvezető-helyettes", "boltvezető",
        "boltvezető-helyettes", "áruházvezető", "műszakvezető",
        "részlegvezető", "osztályvezető", "területi vezető",
        "régióvezető", "manager", "menedzser", "team leader"
    ],
    "recruitment_event": [
        "toborzónap", "nyílt nap", "karriernap", "állásbörze"
    ]
}


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except Exception:
        return None


def clean_text(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_search_url(source_type, company):
    q = urllib.parse.quote_plus(company + " állás")

    if source_type == "job_portal":
        return f"https://www.profession.hu/allasok/1,0,0,{q}"

    if source_type == "indeed":
        return f"https://hu.indeed.com/jobs?q={q}"

    if source_type == "linkedin":
        return f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote_plus(company)}"

    return None


def normalize_title(title):
    title = unescape(title)
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"^\d{4}\s+", "", title)
    title = re.sub(r"^\d{1,2}\s+", "", title)
    title = re.sub(r"\s+\d{1,2}$", "", title)
    title = re.sub(r"^(ma|tegnap|új|állás|részletek|feladva)\s+", "", title, flags=re.I)
    title = title.strip(" -|•,.;:")
    return title


def contains_job_term(title):
    lower = title.lower()
    return any(term in lower for term in FMCG_JOB_TERMS)


def contains_bad_term(title):
    lower = title.lower()
    return any(term in lower for term in BAD_TERMS)


def company_match(company_id, company_name, title, source_type):
    """
    Career sites are company-owned, so strict company matching is not required.
    Job portals are mixed pages, so we need company alias confirmation unless the title is a very clean FMCG role.
    """
    if source_type == "career_site":
        return True

    lower = title.lower()
    aliases = COMPANY_ALIASES.get(company_id, [company_name.lower()])

    if any(alias in lower for alias in aliases):
        return True

    clean_role_patterns = [
        r"^(eladó|bolti eladó|eladó-pénztáros|pénztáros|árufeltöltő)",
        r"^(higiéniai munkatárs|higiénikus)",
        r"^(üzletvezető|üzletvezető-helyettes|boltvezető|boltvezető-helyettes)",
        r"^(raktári dolgozó|raktáros|targoncavezető|pikker|komissiózó)",
        r"^(hentes|pék|cukrász|pékcsomagoló|csemegepult)"
    ]

    return any(re.search(pattern, lower) for pattern in clean_role_patterns)


def is_valid_job_title(title, company_id, company_name, source_type):
    title = normalize_title(title)
    lower = title.lower()

    if not title:
        return False

    if len(title) < 4 or len(title) > 90:
        return False

    if len(title.split()) > 8:
        return False

    if contains_bad_term(title):
        return False

    if not contains_job_term(title):
        return False

    if not company_match(company_id, company_name, title, source_type):
        return False

    if lower in ["eladótérben", "munkatárs", "vezető", "manager", "asszisztens"]:
        return False

    return True


def extract_candidate_lines(text):
    separators = r"[\n\r\t]| {2,}| • | \| "
    parts = re.split(separators, text)
    candidates = []

    for part in parts:
        part = normalize_title(part)
        if part:
            candidates.append(part)

    return candidates


def extract_possible_job_titles(html, company_id, company_name, source_type):
    text = clean_text(html)
    candidates = extract_candidate_lines(text)

    titles = []

    escaped_terms = [re.escape(term) for term in sorted(FMCG_JOB_TERMS, key=len, reverse=True)]
    term_pattern = "|".join(escaped_terms)

    for candidate in candidates:
        if is_valid_job_title(candidate, company_id, company_name, source_type):
            titles.append(normalize_title(candidate))

    short_window_pattern = rf"([A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9 /\-]{{0,20}}(?:{term_pattern})[A-ZÁÉÍÓÖŐÚÜŰa-záéíóöőúüű0-9 /\-]{{0,35}})"

    for match in re.findall(short_window_pattern, text, flags=re.I):
        title = normalize_title(match)
        if is_valid_job_title(title, company_id, company_name, source_type):
            titles.append(title)

    unique = []
    seen = set()

    for title in titles:
        key = title.lower()
        if key not in seen:
            unique.append(title)
            seen.add(key)

    return unique[:80]


def extract_count_hint(html):
    text = clean_text(html).lower()

    patterns = [
        r"(\d{1,4})\s+(?:állás|találat|hirdetés)",
        r"(?:állás|találat|hirdetés)[^\d]{0,20}(\d{1,4})"
    ]

    numbers = []
    current_year = datetime.now(timezone.utc).year

    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                value = int(match)

                if value in {current_year - 1, current_year, current_year + 1}:
                    continue

                if 0 <= value <= 1000:
                    numbers.append(value)

            except ValueError:
                pass

    if not numbers:
        return None

    return max(numbers)


def detect_category(title):
    lower = title.lower()

    if any(word in lower for word in CATEGORY_KEYWORDS["recruitment_event"]):
        return "recruitment_event"

    scores = {}
    for category, words in CATEGORY_KEYWORDS.items():
        if category == "recruitment_event":
            continue
        scores[category] = sum(1 for word in words if word in lower)

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return "unknown"

    return best


def detect_salary(text):
    lower = text.lower()

    salary_patterns = [
        r"(\d{3})\s?000\s?ft",
        r"(\d{3})\s?ezer\s?ft",
        r"bruttó\s+(\d{3})"
    ]

    values = []

    for pattern in salary_patterns:
        for match in re.findall(pattern, lower):
            try:
                value = int(match) * 1000
                if 250000 <= value <= 2500000:
                    values.append(value)
            except ValueError:
                pass

    if not values:
        return None

    return {
        "salary_min_huf": min(values),
        "salary_max_huf": max(values)
    }


def extract_location_from_title(title):
    if " - " not in title:
        return None

    parts = [p.strip() for p in title.split(" - ") if p.strip()]

    if len(parts) < 2:
        return None

    possible_location = parts[-1]
    possible_location = re.sub(r"\s+\d{1,2}$", "", possible_location).strip()

    bad_location_terms = [
        "franchise", "feladva", "magyarország", "élelmisz", "sway",
        "rossma", "sinsay", "tesco-bst"
    ]

    if len(possible_location) > 35:
        return None

    if any(term in possible_location.lower() for term in bad_location_terms):
        return None

    if contains_job_term(possible_location):
        return None

    return possible_location


def posting_id(company_id, source_name, title):
    raw = f"{company_id}|{source_name}|{title}".lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def collect_from_source(company_id, company_name, source):
    source_type = source.get("type")
    source_name = source.get("name")
    base_url = source.get("url")
    enabled = source.get("enabled", True)

    result = {
        "source_name": source_name,
        "source_type": source_type,
        "source_url": base_url,
        "status": "skipped",
        "count_hint": None,
        "postings": [],
        "error": None
    }

    if not enabled:
        result["status"] = "disabled"
        return result

    if source_type in ["facebook", "linkedin"]:
        result["status"] = "manual_or_limited"
        result["error"] = "Ez a forrás automatizáltan korlátozottan gyűjthető."
        return result

    if source_type in ["job_portal", "indeed"]:
        url = make_search_url(source_type, company_name)
    elif source_type == "career_site":
        url = base_url
    else:
        url = base_url

    if not url:
        result["status"] = "no_url"
        return result

    html = fetch_url(url)

    if not html:
        result["status"] = "fetch_failed"
        result["error"] = "Nem sikerült letölteni az oldalt."
        return result

    result["status"] = "fetched"
    result["count_hint"] = extract_count_hint(html)

    titles = extract_possible_job_titles(html, company_id, company_name, source_type)

    for title in titles:
        category = detect_category(title)
        salary = detect_salary(title)

        posting = {
            "posting_id": posting_id(company_id, source_name, title),
            "company_id": company_id,
            "company": company_name,
            "source": source_name,
            "source_type": source_type,
            "title": title,
            "category": category,
            "location": extract_location_from_title(title),
            "salary_min_huf": salary["salary_min_huf"] if salary else None,
            "salary_max_huf": salary["salary_max_huf"] if salary else None,
            "salary_visible": salary is not None,
            "benefits_visible": None,
            "commuting_support_visible": None,
            "full_time_visible": None,
            "part_time_visible": None,
            "url": url
        }

        result["postings"].append(posting)

    time.sleep(REQUEST_DELAY_SECONDS)
    return result


def summarize_company(company, source_results, collected_at):
    company_id = company["id"]
    company_name = company["company"]

    postings = []
    source_statuses = []

    for result in source_results:
        postings.extend(result.get("postings", []))
        source_statuses.append({
            "source_name": result.get("source_name"),
            "source_type": result.get("source_type"),
            "status": result.get("status"),
            "count_hint": result.get("count_hint"),
            "error": result.get("error")
        })

    unique_postings = {}
    for posting in postings:
        unique_postings[posting["posting_id"]] = posting

    postings = list(unique_postings.values())

    category_counts = {
        "store": 0,
        "warehouse": 0,
        "office": 0,
        "management": 0,
        "recruitment_event": 0,
        "unknown": 0
    }

    for posting in postings:
        category = posting.get("category", "unknown")
        if category not in category_counts:
            category = "unknown"
        category_counts[category] += 1

    count_hints = [
        result.get("count_hint")
        for result in source_results
        if isinstance(result.get("count_hint"), int)
    ]

    parsed_postings_count = len(postings)
    external_count_hint = max(count_hints) if count_hints else None
    salary_visible_ads = sum(1 for p in postings if p.get("salary_visible") is True)

    return {
        "id": company_id,
        "company": company_name,
        "snapshot_date": collected_at,

        "total_verified_ads": parsed_postings_count,
        "parsed_postings_count": parsed_postings_count,
        "external_count_hint": external_count_hint,

        "store_jobs": category_counts["store"],
        "warehouse_jobs": category_counts["warehouse"],
        "office_jobs": category_counts["office"],
        "management_jobs": category_counts["management"],
        "recruitment_events": category_counts["recruitment_event"],
        "unknown_jobs": category_counts["unknown"],

        "salary_visible_ads": salary_visible_ads,
        "benefits_visible_ads": None,
        "travel_support_ads": None,
        "bonus_ads": None,
        "cafeteria_ads": None,

        "career_site_present": any(s.get("type") == "career_site" for s in company.get("sources", [])),
        "profession_present": any(s.get("type") == "job_portal" for s in company.get("sources", [])),
        "linkedin_jobs_present": any(s.get("type") == "linkedin" for s in company.get("sources", [])),
        "indeed_present": any(s.get("type") == "indeed" for s in company.get("sources", [])),

        "career_site_active_ads": None,
        "profession_active_ads": None,
        "linkedin_active_ads": None,
        "indeed_active_ads": None,

        "salary_visible_in_examples": salary_visible_ads > 0,
        "benefits_visible_in_examples": None,
        "commuting_support_visible": None,
        "cafeteria_visible": None,
        "bonus_visible": None,
        "training_visible": None,
        "full_time_visible": None,
        "part_time_visible": None,

        "source_confidence": "medium" if parsed_postings_count > 0 else "low",
        "labor_pressure_status": "automatikus gyűjtés előzetes",
        "source_statuses": source_statuses,
        "notes": "Automatikusan gyűjtött előzetes adat. Az external_count_hint a találati oldal becsült darabszáma; a total_verified_ads a részletesen kinyert rekordok száma."
    }, postings


def main():
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    companies = load_json(SOURCES_FILE, [])
    if not companies:
        raise RuntimeError("Hiányzik vagy üres a docs/data/job-sources.json fájl.")

    all_summaries = []
    all_postings = []
    raw_results = []

    for company in companies:
        company_id = company["id"]
        company_name = company["company"]

        source_results = []

        for source in company.get("sources", []):
            result = collect_from_source(company_id, company_name, source)
            source_results.append(result)

        summary, postings = summarize_company(company, source_results, collected_at)

        all_summaries.append(summary)
        all_postings.extend(postings)

        raw_results.append({
            "id": company_id,
            "company": company_name,
            "sources": source_results
        })

    month_name = datetime.now(timezone.utc).strftime("%Y-%m")

    save_json(JOBS_FILE, all_summaries)
    save_json(CURRENT_POSTINGS_FILE, all_postings)

    save_json(HISTORY_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "companies": all_summaries,
        "postings": all_postings
    })

    save_json(RAW_DIR / f"{month_name}.json", {
        "snapshot_date": collected_at,
        "raw_results": raw_results
    })

    status = {
        "last_update": collected_at,
        "companies_tracked": len(companies),
        "summaries_written": len(all_summaries),
        "postings_parsed": len(all_postings),
        "history_file": f"{month_name}.json",
        "raw_file": f"{month_name}.json",
        "mode": "weekly_public_web_collection_hybrid_fmcg_parser_v3"
    }

    save_json(STATUS_FILE, status)

    print("FMCG jobs monitor updated.")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
