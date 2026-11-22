"""SQLite database for persisting scraped jobs and match results."""

import json
import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join("data", "jobs.db")


def get_db(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn=None):
    own = conn is None
    if own:
        conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url TEXT UNIQUE NOT NULL,
            title TEXT,
            company TEXT,
            location TEXT,
            description TEXT,
            salary_min REAL,
            salary_max REAL,
            salary_currency TEXT,
            salary_period TEXT,
            min_experience INTEGER,
            job_type TEXT,
            is_remote INTEGER DEFAULT 0,
            site TEXT,
            date_posted TEXT,
            date_scraped TEXT DEFAULT (datetime('now')),
            search_batch TEXT,
            is_saved INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            match_score INTEGER,
            keyword_score INTEGER,
            context_fit_score INTEGER,
            required_keywords TEXT,
            preferred_keywords TEXT,
            matched_keywords TEXT,
            missing_required_keywords TEXT,
            missing_preferred_keywords TEXT,
            ats_summary TEXT,
            resume_suggestions TEXT,
            missing_bits TEXT,
            matched_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(search_batch);
        CREATE INDEX IF NOT EXISTS idx_jobs_saved ON jobs(is_saved);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(date_posted);
    """)
    conn.commit()
    if own:
        conn.close()


def store_jobs(conn, df, batch_id):
    stored = 0
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT INTO jobs (job_url, title, company, location, description,
                    salary_min, salary_max, salary_currency, salary_period,
                    min_experience, job_type, is_remote, site, date_posted, search_batch)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_url) DO UPDATE SET
                    title=excluded.title, company=excluded.company,
                    description=excluded.description,
                    salary_min=excluded.salary_min, salary_max=excluded.salary_max,
                    salary_currency=excluded.salary_currency,
                    salary_period=excluded.salary_period,
                    min_experience=excluded.min_experience,
                    search_batch=excluded.search_batch
            """, (
                row.get("job_url"),
                row.get("title"),
                row.get("company"),
                row.get("location"),
                row.get("description"),
                _safe_float(row.get("salary_min")),
                _safe_float(row.get("salary_max")),
                row.get("salary_currency"),
                row.get("salary_period"),
                _safe_int(row.get("min_experience")),
                row.get("job_type"),
                1 if row.get("is_remote") else 0,
                row.get("site"),
                str(row["date_posted"]) if row.get("date_posted") is not None else None,
                batch_id,
            ))
            stored += 1
        except Exception as e:
            print(f"  Error storing job: {e}")
    conn.commit()
    return stored


def get_latest_batch(conn):
    row = conn.execute(
        "SELECT search_batch FROM jobs ORDER BY date_scraped DESC LIMIT 1"
    ).fetchone()
    return row["search_batch"] if row else None


def get_stats(conn, preferred_companies=None):
    cutoff = _cutoff_14d()
    batch = get_latest_batch(conn)

    recent = 0
    if batch:
        recent = conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE search_batch = ?", (batch,)
        ).fetchone()["c"]

    all_count = conn.execute(
        "SELECT COUNT(*) AS c FROM jobs WHERE date_scraped >= ?", (cutoff,)
    ).fetchone()["c"]

    saved = conn.execute(
        "SELECT COUNT(*) AS c FROM jobs WHERE is_saved = 1"
    ).fetchone()["c"]

    preferred = 0
    if preferred_companies:
        where, params = _preferred_where(preferred_companies)
        preferred = conn.execute(
            f"SELECT COUNT(*) AS c FROM jobs WHERE ({where}) AND date_scraped >= ?",
            params + [cutoff],
        ).fetchone()["c"]

    return {"recent": recent, "all": all_count, "saved": saved, "preferred": preferred}


def get_jobs(conn, category, preferred_companies=None):
    cutoff = _cutoff_14d()

    if category == "recent":
        batch = get_latest_batch(conn)
        if not batch:
            return []
        rows = conn.execute(
            "SELECT * FROM jobs WHERE search_batch = ? ORDER BY date_posted DESC",
            (batch,),
        ).fetchall()
    elif category == "all":
        rows = conn.execute(
            "SELECT * FROM jobs WHERE date_scraped >= ? ORDER BY date_posted DESC",
            (cutoff,),
        ).fetchall()
    elif category == "saved":
        rows = conn.execute(
            "SELECT * FROM jobs WHERE is_saved = 1 ORDER BY date_posted DESC"
        ).fetchall()
    elif category == "preferred":
        if not preferred_companies:
            return []
        where, params = _preferred_where(preferred_companies)
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE ({where}) AND date_scraped >= ? ORDER BY date_posted DESC",
            params + [cutoff],
        ).fetchall()
    else:
        return []

    return [dict(r) for r in rows]


def get_job(conn, job_id):
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)

    match_row = conn.execute(
        "SELECT * FROM match_results WHERE job_id = ?", (job_id,)
    ).fetchone()
    if match_row:
        m = dict(match_row)
        for field in (
            "required_keywords", "preferred_keywords", "matched_keywords",
            "missing_required_keywords", "missing_preferred_keywords",
            "resume_suggestions", "missing_bits",
        ):
            if m.get(field):
                try:
                    m[field] = json.loads(m[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        job["match"] = m
    else:
        job["match"] = None
    return job


def save_job(conn, job_id):
    conn.execute("UPDATE jobs SET is_saved = 1 WHERE id = ?", (job_id,))
    conn.commit()


def unsave_job(conn, job_id):
    conn.execute("UPDATE jobs SET is_saved = 0 WHERE id = ?", (job_id,))
    conn.commit()


def store_match(conn, job_id, match_data):
    s = {}
    for k, v in match_data.items():
        s[k] = json.dumps(v) if isinstance(v, (list, dict)) else v

    conn.execute("""
        INSERT INTO match_results
            (job_id, match_score, keyword_score, context_fit_score,
             required_keywords, preferred_keywords, matched_keywords,
             missing_required_keywords, missing_preferred_keywords,
             ats_summary, resume_suggestions, missing_bits)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            match_score=excluded.match_score,
            keyword_score=excluded.keyword_score,
            context_fit_score=excluded.context_fit_score,
            required_keywords=excluded.required_keywords,
            preferred_keywords=excluded.preferred_keywords,
            matched_keywords=excluded.matched_keywords,
            missing_required_keywords=excluded.missing_required_keywords,
            missing_preferred_keywords=excluded.missing_preferred_keywords,
            ats_summary=excluded.ats_summary,
            resume_suggestions=excluded.resume_suggestions,
            missing_bits=excluded.missing_bits,
            matched_at=datetime('now')
    """, (
        job_id,
        s.get("match_score"),
        s.get("keyword_score"),
        s.get("context_fit_score"),
        s.get("required_keywords"),
        s.get("preferred_keywords"),
        s.get("matched_keywords"),
        s.get("missing_required_keywords"),
        s.get("missing_preferred_keywords"),
        s.get("ats_summary"),
        s.get("resume_suggestions"),
        s.get("missing_bits"),
    ))
    conn.commit()


# -- helpers --

def _cutoff_14d():
    return (datetime.utcnow() - timedelta(days=14)).isoformat()


def _preferred_where(companies):
    clauses = ["LOWER(company) LIKE ?"] * len(companies)
    params = [f"%{c.lower()}%" for c in companies]
    return " OR ".join(clauses), params


def _safe_float(v):
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None
