"""Generate per-job tailored CV suggestions using Claude."""

import os
import re
from datetime import date

from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1500
BASE_CV_PATH = "config/base_cv.md"
APPLICATIONS_DIR = "applications"

PROMPT_TEMPLATE = """You are a CV tailoring expert. Given a candidate's base CV and a specific job posting, produce a tailored version of the CV in markdown.

Rules:
- Keep all truthful content. Do not fabricate experience.
- Reorder bullet points to lead with the most relevant ones for this job.
- Adjust wording to echo the job posting's keywords where honest.
- Add a 2-line "Summary" section at the top tailored to this specific role.
- At the end, add a section "## Changes Made" listing each change and why.

BASE CV:
{base_cv}

JOB POSTING:
Title: {title}
Company: {company}
Description: {description}
"""


def _sanitize(name: str) -> str:
    name = str(name).strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_-]", "", name)
    return name


def _read_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def tailor_job(
    job: dict,
    base_cv_path: str = BASE_CV_PATH,
    applications_dir: str = APPLICATIONS_DIR,
) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = Anthropic(api_key=api_key)

    base_cv = _read_file(base_cv_path)

    title = job.get("title", "")
    company = job.get("company", "")
    description = job.get("description", "")
    job_url = job.get("job_url", "")

    prompt = PROMPT_TEMPLATE.format(
        base_cv=base_cv,
        title=title,
        company=company,
        description=description,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    tailored_cv = response.content[0].text

    today = date.today().isoformat()
    folder_name = f"{_sanitize(company)}_{_sanitize(title)}_{today}"
    folder_path = os.path.join(applications_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    with open(os.path.join(folder_path, "tailored_cv.md"), "w") as f:
        f.write(tailored_cv)

    job_details = (
        f"# Job Details\n\n"
        f"**Title:** {title}\n\n"
        f"**Company:** {company}\n\n"
        f"**URL:** {job_url}\n\n"
        f"## Description\n\n{description}\n"
    )
    with open(os.path.join(folder_path, "job_details.md"), "w") as f:
        f.write(job_details)

    print(f"Generated suggestions for {company} - {title}")
    return folder_path


if __name__ == "__main__":
    sample_job = {
        "title": "Software Developer",
        "company": "Example Corp",
        "description": "We are looking for a Python developer with ML experience.",
        "job_url": "https://example.com/job/1",
    }
    tailor_job(sample_job)
