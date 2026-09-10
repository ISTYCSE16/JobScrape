"""Score each scraped job against the candidate's skills/CV using Claude (Haiku)."""

import json
import os
import time

import pandas as pd
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
SKILLS_PATH = "config/skills.md"
BASE_CV_PATH = "config/base_cv.md"
SLEEP_SECONDS = 0.5
MAX_TOKENS = 500

PROMPT_TEMPLATE = """You are a job-match analyst. Given a candidate's skills/experience and a job posting, return ONLY a JSON object (no markdown, no explanation):

{{
  "match_score": <0-100 integer>,
  "strong_keywords": ["keyword1", "keyword2", ...],
  "missing_keywords": ["keyword1", "keyword2", ...],
  "cv_changes_summary": "One paragraph: what specific lines/sections of the CV should change for this job"
}}

CANDIDATE SKILLS:
{skills}

CANDIDATE CV:
{cv}

JOB POSTING:
Title: {title}
Company: {company}
Description: {description}
"""


def _read_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def _parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def score_jobs(
    df: pd.DataFrame,
    skills_path: str = SKILLS_PATH,
    base_cv_path: str = BASE_CV_PATH,
) -> pd.DataFrame:
    if df.empty:
        return df

    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    skills = _read_file(skills_path)
    cv = _read_file(base_cv_path)

    scored = df.copy()
    match_scores = []
    strong_keywords_list = []
    missing_keywords_list = []
    cv_changes_summaries = []

    total = len(scored)
    for i, row in enumerate(scored.itertuples(index=False), start=1):
        print(f"Scoring job {i} of {total}...")

        prompt = PROMPT_TEMPLATE.format(
            skills=skills,
            cv=cv,
            title=getattr(row, "title", ""),
            company=getattr(row, "company", ""),
            description=getattr(row, "description", ""),
        )

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            parsed = _parse_response(raw_text)

            match_scores.append(parsed.get("match_score", -1))
            strong_keywords_list.append(parsed.get("strong_keywords", []))
            missing_keywords_list.append(parsed.get("missing_keywords", []))
            cv_changes_summaries.append(parsed.get("cv_changes_summary", ""))
        except Exception as e:
            print(f"  ERROR scoring job {i}: {e}")
            match_scores.append(-1)
            strong_keywords_list.append([])
            missing_keywords_list.append([])
            cv_changes_summaries.append("")

        time.sleep(SLEEP_SECONDS)

    scored["match_score"] = match_scores
    scored["strong_keywords"] = strong_keywords_list
    scored["missing_keywords"] = missing_keywords_list
    scored["cv_changes_summary"] = cv_changes_summaries

    scored = scored.sort_values("match_score", ascending=False).reset_index(drop=True)
    return scored


if __name__ == "__main__":
    sample = pd.DataFrame(
        [
            {
                "site": "linkedin",
                "title": "Software Developer",
                "company": "Example Corp",
                "location": "Edmonton, AB",
                "job_url": "https://example.com/job/1",
                "description": "We are looking for a Python developer with ML experience.",
                "date_posted": "2026-09-09",
                "job_type": "fulltime",
                "hours_since_posted": 12,
            }
        ]
    )
    print(score_jobs(sample))
