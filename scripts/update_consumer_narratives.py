import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = DATA_DIR / "consumer-narratives.json"

INPUT_FILES = {
    "news": DATA_DIR / "news-social.json",
    "social": DATA_DIR / "social-monitor.json",
    "linkedin": DATA_DIR / "linkedin-recruitment-intelligence.json",
    "jobs": DATA_DIR / "job-monitor.json",
}

COMPANIES = [
    {"id": "lidl", "company": "Lidl"},
    {"id": "aldi", "company": "ALDI"},
    {"id": "penny", "company": "Penny"},
    {"id": "spar", "company": "SPAR"},
    {"id": "tesco", "company": "Tesco"},
    {"id": "auchan", "company": "Auchan"},
]

NARRATIVES = {
    "promotion_attention": {
        "label": "Akció / promóció",
        "keywords": [
            "akció", "akcios", "akciós", "kupon", "kedvezmény", "kedvezmeny",
            "újság", "ujsag", "promóció", "promocio", "olcsó", "olcso",
            "leárazás", "learazas", "árengedmény", "arengedmeny"
        ],
    },
    "price_sensitivity": {
        "label": "Árérzékenység",
        "keywords": [
            "ár", "ar", "árak", "arak", "drága", "draga", "drágulás", "dragulas",
            "infláció", "inflacio", "olcsó", "olcso", "árstop", "arstop",
            "árverseny", "arverseny", "bevásárlás drága", "dragabb"
        ],
    },
    "employment_attention": {
        "label": "Munkaerő / állás",
        "keywords": [
            "állás", "allas", "karrier", "munka", "munkahely", "fizetés", "fizetes",
            "béremelés", "beremeles", "toborzás", "toborzas", "munkavállaló",
            "munkavallalo", "dolgozó", "dolgozo", "raktár", "raktar", "logisztika"
        ],
    },
    "customer_experience": {
        "label": "Vásárlói élmény",
        "keywords": [
            "sor", "kassza", "parkoló", "parkolo", "panasz", "reklamáció",
            "reklamacio", "probléma", "problema", "kiszolgálás", "kiszolgalas",
            "ügyfélszolgálat", "ugyfelszolgalat", "bolt", "áruház", "aruhaz"
        ],
    },
    "digital_attention": {
        "label": "Digitális / app / online",
        "keywords": [
            "app", "alkalmazás", "alkalmazas", "online", "webshop", "webáruház",
            "webaruhaz", "online rendelés", "online rendeles", "clubcard",
            "digitális", "digitalis", "önkiszolgáló", "onkiszolgalo"
        ],
    },
}

SOURCE_WEIGHTS = {
    "news": 1.2,
    "social": 1.5,
    "linkedin": 1.1,
    "jobs": 1.0,
}


def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize(text):
    if text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def keyword_score(text, keywords):
    t = normalize(text)
    score = 0

    for kw in keywords:
        k = normalize(kw)
        if not k:
            continue

        if " " in k:
            if k in t:
                score += 3
        else:
            matches = re.findall(rf"\b{re.escape(k)}\b", t)
            score += len(matches)

    return score


def clamp(value, low=0, high=100):
    try:
        value = float(value)
    except Exception:
        value = 0
    return max(low, min(high, round(value)))


def get_company_name_from_id(cid):
    for c in COMPANIES:
        if c["id"] == cid:
            return c["company"]
    return cid


def collect_news_texts(news_data, company):
    texts = []

    if not news_data:
        return texts

    for c in news_data.get("companies", []):
        if normalize(c.get("company")) == normalize(company):
            parts = [
                c.get("company"),
                c.get("highlight_event"),
                c.get("dominant_market_narrative"),
                c.get("dominant_strategic_narrative_label"),
                c.get("dominant_business_impact_label"),
            ]

            for field in ["business_impacts", "strategic_narratives"]:
                obj = c.get(field, {})
                if isinstance(obj, dict):
                    parts.extend(obj.keys())

            texts.append(" ".join([str(x) for x in parts if x]))

    for ev in news_data.get("events", []) + news_data.get("top_events", []):
        full = " ".join([
            str(ev.get("company", "")),
            str(ev.get("title", "")),
            str(ev.get("summary", "")),
            str(ev.get("source", "")),
            str(ev.get("business_impact", "")),
            str(ev.get("strategic_narrative", "")),
        ])

        if normalize(company) in normalize(full):
            texts.append(full)

    return texts


def collect_social_texts(social_data, company):
    texts = []

    if not social_data:
        return texts

    for item in social_data.get("items", []):
        if normalize(item.get("company")) == normalize(company):
            parts = [
                item.get("company"),
                item.get("dominant_social_topic"),
                item.get("social_sentiment"),
            ]

            for topic in item.get("top_social_topics", []) or []:
                parts.append(topic.get("topic"))
                parts.append(topic.get("label"))
                parts.append(topic.get("summary"))

            texts.append(" ".join([str(x) for x in parts if x]))

    for key in ["raw_items", "dashboard_items", "background_items", "hu_relevant_items"]:
        for item in social_data.get(key, []) or []:
            full = " ".join([
                str(item.get("company", "")),
                str(item.get("title", "")),
                str(item.get("summary", "")),
                str(item.get("text", "")),
                str(item.get("source", "")),
                str(item.get("url", "")),
            ])

            if normalize(company) in normalize(full):
                texts.append(full)

    return texts


def collect_linkedin_texts(linkedin_data, company):
    texts = []

    if not linkedin_data:
        return texts

    for c in linkedin_data.get("companies", []):
        if normalize(c.get("company")) == normalize(company):
            parts = [
                c.get("company"),
                c.get("recruitment_focus"),
                c.get("recruitment_level"),
                c.get("interpretation"),
            ]

            scores = c.get("category_scores", {})
            if isinstance(scores, dict):
                parts.extend(scores.keys())

            texts.append(" ".join([str(x) for x in parts if x]))

    return texts


def collect_jobs_texts(job_data, company):
    texts = []

    if not job_data:
        return texts

    possible_lists = []

    if isinstance(job_data.get("jobs"), list):
        possible_lists.append(job_data.get("jobs"))

    if isinstance(job_data.get("items"), list):
        possible_lists.append(job_data.get("items"))

    if isinstance(job_data.get("postings"), list):
        possible_lists.append(job_data.get("postings"))

    for block in possible_lists:
        for item in block:
            full = " ".join([
                str(item.get("company", "")),
                str(item.get("title", "")),
                str(item.get("summary", "")),
                str(item.get("location", "")),
                str(item.get("source", "")),
            ])

            if normalize(company) in normalize(full):
                texts.append(full)

    return texts


def build_source_scores(texts, source_name):
    source_score = {key: 0 for key in NARRATIVES.keys()}

    combined = " ".join(texts)

    for narrative_id, narrative in NARRATIVES.items():
        raw = keyword_score(combined, narrative["keywords"])
        weighted = raw * SOURCE_WEIGHTS.get(source_name, 1.0)
        source_score[narrative_id] = weighted

    return source_score


def merge_scores(source_scores):
    merged = {key: 0 for key in NARRATIVES.keys()}

    for source_name, scores in source_scores.items():
        for k, v in scores.items():
            merged[k] += v

    return merged


def scale_scores(merged):
    max_score = max(merged.values()) if merged else 0

    if max_score <= 0:
        return {k: 0 for k in merged.keys()}

    return {
        k: clamp((v / max_score) * 100)
        for k, v in merged.items()
    }


def dominant_narrative(scaled):
    if not scaled:
        return None

    key = max(scaled, key=lambda x: scaled[x])

    if scaled.get(key, 0) <= 0:
        return None

    return key


def build_company(company, datasets):
    news_texts = collect_news_texts(datasets["news"], company["company"])
    social_texts = collect_social_texts(datasets["social"], company["company"])
    linkedin_texts = collect_linkedin_texts(datasets["linkedin"], company["company"])
    jobs_texts = collect_jobs_texts(datasets["jobs"], company["company"])

    source_scores = {
        "news": build_source_scores(news_texts, "news"),
        "social": build_source_scores(social_texts, "social"),
        "linkedin": build_source_scores(linkedin_texts, "linkedin"),
        "jobs": build_source_scores(jobs_texts, "jobs"),
    }

    merged = merge_scores(source_scores)
    scaled = scale_scores(merged)
    dominant = dominant_narrative(scaled)

    evidence_counts = {
        "news_texts": len(news_texts),
        "social_texts": len(social_texts),
        "linkedin_texts": len(linkedin_texts),
        "jobs_texts": len(jobs_texts),
    }

    confidence_points = sum(1 for v in evidence_counts.values() if v > 0)

    if confidence_points >= 3:
        confidence = "high"
    elif confidence_points == 2:
        confidence = "medium"
    elif confidence_points == 1:
        confidence = "low"
    else:
        confidence = "no_data"

    if dominant:
        interpretation = (
            f"{company['company']} esetében a legerősebb fogyasztói narratíva: "
            f"{NARRATIVES[dominant]['label']}."
        )
    else:
        interpretation = (
            f"{company['company']} esetében jelenleg nincs elegendő fogyasztói narratíva-jel."
        )

    return {
        "id": company["id"],
        "company": company["company"],
        "confidence": confidence,
        "dominant_narrative": dominant,
        "dominant_narrative_label": NARRATIVES[dominant]["label"] if dominant else None,
        "scores": scaled,
        "raw_scores": merged,
        "source_scores": source_scores,
        "evidence_counts": evidence_counts,
        "interpretation": interpretation,
    }


def main():
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    datasets = {
        key: load_json(path)
        for key, path in INPUT_FILES.items()
    }

    companies = [
        build_company(company, datasets)
        for company in COMPANIES
    ]

    valid_companies = [c for c in companies if c["confidence"] != "no_data"]

    leader = None
    if valid_companies:
        leader = sorted(
            valid_companies,
            key=lambda x: max(x["scores"].values()) if x.get("scores") else 0,
            reverse=True
        )[0]

    output = {
        "updated_at": updated_at,
        "status": "ok" if valid_companies else "fallback_no_data",
        "source": "local_fmcg_osint_layers",
        "method": "keyword_weighted_consumer_narrative_engine_v1",
        "important_note": (
            "Ez nem Google Trends adat és nem reprezentatív fogyasztói kutatás. "
            "A mutató a meglévő helyi OSINT rétegekből képzett kulcsszavas narratíva-indikátor."
        ),
        "input_files": {key: str(path.relative_to(BASE_DIR)) for key, path in INPUT_FILES.items()},
        "narrative_labels": {key: value["label"] for key, value in NARRATIVES.items()},
        "leader": leader,
        "companies": companies,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
