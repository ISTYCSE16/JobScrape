"""Score each scraped job against the candidate's skills/CV using an ATS-style model.

Real Applicant Tracking Systems rank candidates mainly by deterministic keyword
coverage against the job's stated requirements (required vs. preferred/nice-to-have
qualifications), not by a single subjective "vibe" score. This module follows that
practice:

1. One Claude call per job extracts structured hiring requirements from the
   posting: required keywords (must-have hard skills/tools), preferred keywords
   (nice-to-have), and a qualitative context-fit score (seniority/career
   trajectory fit that plain keyword matching can't capture).
2. Python then deterministically checks which of those keywords actually appear
   in the candidate's skills/CV text (word-boundary matching, like an ATS parser).
3. The final match_score is a weighted blend: 65% keyword coverage (required
   keywords count double vs. preferred) + 35% context fit.

This makes the score auditable: `keyword_score`, `context_fit_score`,
`matched_keywords`, and `missing_*_keywords` are all kept on the DataFrame so the
web report can show exactly why a job scored the way it did.
"""

import json
import os
import re
import time

import pandas as pd
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
SKILLS_PATH = "config/skills.md"
BASE_CV_PATH = "config/base_cv.md"
SLEEP_SECONDS = 0.5
MAX_TOKENS = 600

# ATS weighting: required keywords matter more than preferred; keyword coverage
# matters more than the softer, subjective context-fit judgment.
REQUIRED_KEYWORD_WEIGHT = 2
PREFERRED_KEYWORD_WEIGHT = 1
KEYWORD_COVERAGE_WEIGHT = 0.65
CONTEXT_FIT_WEIGHT = 0.35

PROMPT_TEMPLATE = """You are an ATS (Applicant Tracking System) requirements extractor. Analyze the job posting and extract structured hiring requirements the way an ATS keyword parser would. Return ONLY a JSON object (no markdown, no explanation):

{{
  "job_title_core": "<normalized core title, e.g. 'Software Developer'>",
  "seniority_level": "<entry|junior|mid|senior|lead|unspecified>",
  "required_keywords": ["<hard skills, tools, languages, frameworks, certifications explicitly required or listed as minimum qualifications>"],
  "preferred_keywords": ["<hard skills/tools mentioned as nice-to-have, preferred, or a bonus>"],
  "min_years_experience": <integer or null>,
  "context_fit_score": <0-100 integer judging how well the candidate's overall background, seniority, and career trajectory fit this role based on the full CV/skills, independent of keyword overlap>,
  "cv_changes_summary": "One paragraph: what specific lines/sections of the CV should change for this job"
}}

Extraction rules:
- required_keywords / preferred_keywords must be short, canonical tokens (e.g. "Python", "AWS", "CI/CD", "Docker"), not full sentences.
- Only extract hard skills, tools, technologies, platforms, and certifications — never soft skills like "communication" or "team player".
- required_keywords = things stated as required / must-have / minimum qualifications.
- preferred_keywords = things stated as preferred / nice-to-have / bonus / plus.

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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def _keyword_found(keyword: str, haystack_norm: str) -> bool:
    kw = _normalize(keyword)
    if not kw:
        return False
    pattern = re.escape(kw)
    if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", haystack_norm):
        return True
    return kw in haystack_norm


def _match_keywords(keywords: list, haystack_norm: str) -> tuple:
    matched, missing = [], []
    for kw in keywords or []:
        (matched if _keyword_found(kw, haystack_norm) else missing).append(kw)
    return matched, missing


def _keyword_coverage(n_matched_required, n_required, n_matched_preferred, n_preferred):
    numerator = (
        n_matched_required * REQUIRED_KEYWORD_WEIGHT
        + n_matched_preferred * PREFERRED_KEYWORD_WEIGHT
    )
    denominator = (
        n_required * REQUIRED_KEYWORD_WEIGHT + n_preferred * PREFERRED_KEYWORD_WEIGHT
    )
    if denominator == 0:
        return None
    return 100 * numerator / denominator


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
    candidate_text_norm = _normalize(f"{skills}\n{cv}")

    scored = df.copy()
    columns = {
        "match_score": [],
        "keyword_score": [],
        "context_fit_score": [],
        "job_title_core": [],
        "seniority_level": [],
        "required_keywords": [],
        "preferred_keywords": [],
        "matched_keywords": [],
        "strong_keywords": [],
        "missing_required_keywords": [],
        "missing_preferred_keywords": [],
        "missing_keywords": [],
        "cv_changes_summary": [],
    }

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

            required_keywords = parsed.get("required_keywords", []) or []
            preferred_keywords = parsed.get("preferred_keywords", []) or []
            context_fit_score = parsed.get("context_fit_score")

            matched_required, missing_required = _match_keywords(
                required_keywords, candidate_text_norm
            )
            matched_preferred, missing_preferred = _match_keywords(
                preferred_keywords, candidate_text_norm
            )

            keyword_score = _keyword_coverage(
                len(matched_required),
                len(required_keywords),
                len(matched_preferred),
                len(preferred_keywords),
            )

            if keyword_score is None and context_fit_score is None:
                final_score = -1
            elif keyword_score is None:
                final_score = round(context_fit_score)
            elif context_fit_score is None:
                final_score = round(keyword_score)
            else:
                final_score = round(
                    KEYWORD_COVERAGE_WEIGHT * keyword_score
                    + CONTEXT_FIT_WEIGHT * context_fit_score
                )
            final_score = max(0, min(100, final_score))

            columns["match_score"].append(final_score)
            columns["keyword_score"].append(
                round(keyword_score) if keyword_score is not None else None
            )
            columns["context_fit_score"].append(context_fit_score)
            columns["job_title_core"].append(parsed.get("job_title_core", ""))
            columns["seniority_level"].append(parsed.get("seniority_level", ""))
            columns["required_keywords"].append(required_keywords)
            columns["preferred_keywords"].append(preferred_keywords)
            columns["matched_keywords"].append(matched_required + matched_preferred)
            columns["strong_keywords"].append(matched_required + matched_preferred)
            columns["missing_required_keywords"].append(missing_required)
            columns["missing_preferred_keywords"].append(missing_preferred)
            columns["missing_keywords"].append(missing_required + missing_preferred)
            columns["cv_changes_summary"].append(parsed.get("cv_changes_summary", ""))
        except Exception as e:
            print(f"  ERROR scoring job {i}: {e}")
            columns["match_score"].append(-1)
            columns["keyword_score"].append(None)
            columns["context_fit_score"].append(None)
            columns["job_title_core"].append("")
            columns["seniority_level"].append("")
            columns["required_keywords"].append([])
            columns["preferred_keywords"].append([])
            columns["matched_keywords"].append([])
            columns["strong_keywords"].append([])
            columns["missing_required_keywords"].append([])
            columns["missing_preferred_keywords"].append([])
            columns["missing_keywords"].append([])
            columns["cv_changes_summary"].append("")

        time.sleep(SLEEP_SECONDS)

    for col, values in columns.items():
        scored[col] = values

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
