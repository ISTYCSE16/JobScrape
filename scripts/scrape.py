"""JobSpy scraping: config -> combined, deduplicated pandas DataFrame."""

import os
import re
from datetime import datetime, timezone

import pandas as pd
import yaml
from jobspy import scrape_jobs

SEARCH_CRITERIA_PATH = "config/search_criteria.yaml"
CRITERIA_PATH = "config/criteria.yaml"

OUTPUT_COLUMNS = [
    "site",
    "title",
    "company",
    "location",
    "job_url",
    "description",
    "date_posted",
    "job_type",
    "is_remote",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "min_experience",
]

JOBSPY_SALARY_MAP = {
    "min_amount": "salary_min",
    "max_amount": "salary_max",
    "currency": "salary_currency",
    "interval": "salary_period",
}


def load_criteria(path=None):
    if path is None and os.path.exists(SEARCH_CRITERIA_PATH):
        return _load_search_criteria(SEARCH_CRITERIA_PATH)
    return _load_legacy(path or CRITERIA_PATH)


def _load_search_criteria(path):
    with open(path) as f:
        config = yaml.safe_load(f)
    s = config.get("searches", {})
    titles = s.get("titles", [])
    locations = s.get("locations", [])
    distance = s.get("distance", 50)
    searches = []
    for title in titles:
        for loc in locations:
            loc_name = loc if isinstance(loc, str) else loc.get("name", loc)
            searches.append({
                "term": title,
                "location": loc_name,
                "distance": distance,
                "job_type": "fulltime",
            })
    return {
        "searches": searches,
        "sites": config.get("sites", []),
        "hours_old": config.get("hours_old", 72),
        "results_wanted": config.get("results_wanted", 25),
        "country_indeed": config.get("country_indeed", "canada"),
        "max_experience": config.get("experience", {}).get("max_years"),
    }


def _load_legacy(path):
    with open(path) as f:
        config = yaml.safe_load(f)
    return {
        "searches": config.get("searches", []),
        "sites": config.get("sites", []),
        "hours_old": config.get("hours_old", 24),
        "results_wanted": config.get("results_wanted", 25),
        "country_indeed": config.get("country_indeed", "canada"),
        "max_experience": None,
    }


def _compute_hours_since_posted(date_posted) -> float:
    if pd.isna(date_posted):
        return float("inf")
    posted = pd.to_datetime(date_posted, utc=True, errors="coerce")
    if pd.isna(posted):
        return float("inf")
    now = datetime.now(timezone.utc)
    delta = now - posted.to_pydatetime()
    return round(delta.total_seconds() / 3600, 1)


_EXP_PATTERNS = [
    re.compile(r"minimum\s+(?:of\s+)?(\d+)\s*(?:years?|yrs?)", re.I),
    re.compile(r"at\s+least\s+(\d+)\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d+)\s*[-–]+\s*\d+\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+)?(?:experience|exp)", re.I),
    re.compile(r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+|hands[- ]on\s+)?(?:experience|exp)", re.I),
]
_ENTRY_TERMS = ["entry level", "entry-level", "new grad", "recent graduate", "no experience required"]


def extract_min_experience(text):
    if not isinstance(text, str):
        return None
    lower = text.lower()
    for pat in _EXP_PATTERNS:
        m = pat.search(lower)
        if m:
            return int(m.group(1))
    if any(t in lower for t in _ENTRY_TERMS):
        return 0
    return None


def _prepare_batch(df, max_exp):
    """Normalize a single search result DataFrame for storage."""
    for src, dst in JOBSPY_SALARY_MAP.items():
        if src in df.columns:
            df = df.rename(columns={src: dst})

    if "min_experience" not in df.columns:
        df["min_experience"] = df["description"].apply(extract_min_experience)

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df.drop_duplicates(subset=["job_url"], keep="first")

    filtered = 0
    if max_exp is not None:
        before = len(df)
        df = df[df["min_experience"].isna() | (df["min_experience"] <= max_exp)]
        filtered = before - len(df)

    df = df[OUTPUT_COLUMNS].copy()
    df["hours_since_posted"] = df["date_posted"].apply(_compute_hours_since_posted)
    return df, filtered


def scrape_iter(config_path=None, stop_event=None):
    """Generator that yields progress dicts while scraping.

    Each successful search yields its prepared DataFrame immediately
    so the caller can store it in the DB right away.

    Event types:
        start       — {"type":"start", "total_searches": N}
        searching   — {"type":"searching", "index": i, "term": ..., "location": ...}
        result      — {"type":"result", "index": i, ..., "count": N, "dataframe": df}
        error       — {"type":"error", "index": i, ..., "message": ...}
        done        — {"type":"done", "total": N, "filtered": N}
        stopped     — {"type":"stopped"}
    """
    criteria = load_criteria(config_path)
    sites = criteria["sites"]
    hours_old = criteria["hours_old"]
    results_wanted = criteria["results_wanted"]
    country_indeed = criteria["country_indeed"]
    max_exp = criteria.get("max_experience")
    searches = criteria["searches"]

    yield {"type": "start", "total_searches": len(searches)}

    total_jobs = 0
    total_filtered = 0

    for i, search in enumerate(searches):
        if stop_event and stop_event.is_set():
            yield {"type": "stopped"}
            return

        term = search.get("term")
        location = search.get("location")
        distance = search.get("distance")
        job_type = search.get("job_type")

        yield {"type": "searching", "index": i, "term": term, "location": location}

        try:
            jobs_df = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=location,
                distance=distance,
                job_type=job_type,
                results_wanted=results_wanted,
                hours_old=hours_old,
                country_indeed=country_indeed,
            )
        except Exception as e:
            yield {"type": "error", "index": i, "term": term, "location": location, "message": str(e)}
            continue

        if jobs_df is None or jobs_df.empty:
            yield {"type": "result", "index": i, "term": term, "location": location, "count": 0}
            continue

        prepared, filtered = _prepare_batch(jobs_df.copy(), max_exp)
        total_jobs += len(prepared)
        total_filtered += filtered
        yield {
            "type": "result", "index": i, "term": term, "location": location,
            "count": len(prepared), "dataframe": prepared,
        }

    yield {"type": "done", "total": total_jobs, "filtered": total_filtered}


def scrape_all(config_path=None) -> pd.DataFrame:
    all_frames = []
    for event in scrape_iter(config_path):
        if event["type"] == "searching":
            print(f"Searching: '{event['term']}' in '{event['location']}'...")
        elif event["type"] == "result":
            if event["count"] == 0:
                print(f"  No results for '{event['term']}' in '{event['location']}'")
            else:
                print(f"  Found {event['count']} jobs")
                if "dataframe" in event:
                    all_frames.append(event["dataframe"])
        elif event["type"] == "error":
            print(f"  ERROR: {event['message']}")
        elif event["type"] == "done":
            print(f"Total jobs scraped: {event['total']}")
            if event["filtered"]:
                print(f"  Filtered {event['filtered']} jobs exceeding experience requirement")
    if all_frames:
        return pd.concat(all_frames, ignore_index=True).drop_duplicates(
            subset=["job_url"], keep="first"
        ).reset_index(drop=True)
    return pd.DataFrame(columns=OUTPUT_COLUMNS + ["hours_since_posted"])


if __name__ == "__main__":
    df = scrape_all()
    print(df.head())
