"""On-demand per-job matching via Claude API.

Called when the user clicks "Match Job" in the web UI. Returns ATS breakdown,
resume suggestions, and missing-qualifications analysis in one call.
"""

import json
import os
import re

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
SKILLS_PATH = "config/skills.md"
BASE_CV_PATH = "config/base_cv.md"
MAX_TOKENS = 2000

REQUIRED_KEYWORD_WEIGHT = 2
PREFERRED_KEYWORD_WEIGHT = 1
KEYWORD_COVERAGE_WEIGHT = 0.65
CONTEXT_FIT_WEIGHT = 0.35

MATCH_PROMPT = """You are an expert ATS (Applicant Tracking System) analyst and resume advisor. Analyze the job posting against the candidate's profile comprehensively.

Return ONLY a JSON object (no markdown, no explanation):

{{
  "ats": {{
    "required_keywords": ["<hard skills/tools/technologies/certifications explicitly required — short canonical tokens like 'Python', 'AWS', 'CI/CD'>"],
    "preferred_keywords": ["<hard skills/tools mentioned as nice-to-have/preferred/bonus — short canonical tokens>"],
    "context_fit_score": <0-100 integer: how well the candidate's background, seniority, and career trajectory fit this role, independent of keyword overlap>,
    "seniority_level": "<entry|junior|mid|senior|lead|unspecified>",
    "summary": "<2-3 sentence overall ATS assessment>"
  }},
  "resume_suggestions": [
    {{
      "section": "<CV section name, e.g. 'Experience - Company Name' or 'Technical Skills' or 'Summary'>",
      "changes": [
        {{
          "type": "<keep|modify|remove|add|reorder>",
          "target": "<specific bullet or item being changed>",
          "suggestion": "<exact new text to use, or explanation of why to keep/remove>",
          "reason": "<why this change helps for this specific job>"
        }}
      ]
    }}
  ],
  "missing_bits": [
    {{
      "qualification": "<specific missing skill or qualification>",
      "importance": "<critical|important|nice-to-have>",
      "impact_score": <1-10>,
      "description": "<why this matters for the role>",
      "mitigation": "<how to address the gap: transferable skills, projects, certifications>"
    }}
  ]
}}

Rules:
- required_keywords/preferred_keywords: short canonical tokens only, never sentences. Only hard skills, tools, technologies, certifications — never soft skills.
- resume_suggestions: reference specific CV sections and bullets by name. Be precise — "Change 'Used Docker' to 'Containerized microservices using Docker, reducing deployment time by 40%'" not "Add more detail."
- missing_bits: only genuinely missing qualifications, not things already in the CV.

CANDIDATE SKILLS:
{skills}

CANDIDATE CV:
{cv}

JOB POSTING:
Title: {title}
Company: {company}
Description: {description}
"""


def _read_file(path):
    with open(path) as f:
        return f.read()


def _normalize(text):
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def _keyword_found(keyword, haystack_norm):
    kw = _normalize(keyword)
    if not kw:
        return False
    pattern = re.escape(kw)
    if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", haystack_norm):
        return True
    return kw in haystack_norm


def _keyword_coverage(n_mr, n_r, n_mp, n_p):
    num = n_mr * REQUIRED_KEYWORD_WEIGHT + n_mp * PREFERRED_KEYWORD_WEIGHT
    den = n_r * REQUIRED_KEYWORD_WEIGHT + n_p * PREFERRED_KEYWORD_WEIGHT
    if den == 0:
        return None
    return 100 * num / den


def _parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


def match_job(job, skills_path=SKILLS_PATH, cv_path=BASE_CV_PATH):
    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    skills = _read_file(skills_path)
    cv = _read_file(cv_path)
    candidate_text = _normalize(f"{skills}\n{cv}")

    prompt = MATCH_PROMPT.format(
        skills=skills,
        cv=cv,
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=job.get("description", ""),
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    parsed = _parse_response(response.content[0].text)

    ats = parsed.get("ats", {})
    required_kw = ats.get("required_keywords", []) or []
    preferred_kw = ats.get("preferred_keywords", []) or []
    context_fit = ats.get("context_fit_score")

    matched_req = [kw for kw in required_kw if _keyword_found(kw, candidate_text)]
    missing_req = [kw for kw in required_kw if not _keyword_found(kw, candidate_text)]
    matched_pref = [kw for kw in preferred_kw if _keyword_found(kw, candidate_text)]
    missing_pref = [kw for kw in preferred_kw if not _keyword_found(kw, candidate_text)]

    kw_score = _keyword_coverage(
        len(matched_req), len(required_kw), len(matched_pref), len(preferred_kw)
    )

    if kw_score is None and context_fit is None:
        final = -1
    elif kw_score is None:
        final = round(context_fit)
    elif context_fit is None:
        final = round(kw_score)
    else:
        final = round(KEYWORD_COVERAGE_WEIGHT * kw_score + CONTEXT_FIT_WEIGHT * context_fit)
    final = max(0, min(100, final))

    return {
        "match_score": final,
        "keyword_score": round(kw_score) if kw_score is not None else None,
        "context_fit_score": context_fit,
        "required_keywords": required_kw,
        "preferred_keywords": preferred_kw,
        "matched_keywords": matched_req + matched_pref,
        "missing_required_keywords": missing_req,
        "missing_preferred_keywords": missing_pref,
        "ats_summary": ats.get("summary", ""),
        "resume_suggestions": parsed.get("resume_suggestions", []),
        "missing_bits": parsed.get("missing_bits", []),
    }
