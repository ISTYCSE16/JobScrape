"""Flask web server for the JobScrape dashboard."""

import json
import logging
import os
import threading

from dotenv import load_dotenv
load_dotenv()

import yaml
from flask import Flask, Response, jsonify, render_template, request

from scripts.database import (
    get_db,
    get_job,
    get_jobs,
    get_stats,
    init_db,
    save_job,
    store_jobs,
    store_match,
    unsave_job,
)
from scripts.matcher import match_job

app = Flask(__name__)

_scrape_stop = threading.Event()

LOG_DIR = "data"
LOG_FILE = os.path.join(LOG_DIR, "scrape.log")
os.makedirs(LOG_DIR, exist_ok=True)
_scrape_logger = logging.getLogger("scrape")
_scrape_logger.setLevel(logging.INFO)
_fh = logging.FileHandler(LOG_FILE)
_fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
_scrape_logger.addHandler(_fh)

SEARCH_CRITERIA_PATH = "config/search_criteria.yaml"

_config_cache = None


def _load_config():
    global _config_cache
    if _config_cache is None:
        try:
            with open(SEARCH_CRITERIA_PATH) as f:
                _config_cache = yaml.safe_load(f)
        except FileNotFoundError:
            _config_cache = {}
    return _config_cache


def _load_preferred_companies():
    return _load_config().get("preferred_companies", [])


def _load_location_priority():
    return _load_config().get("location_priority", {})


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    try:
        return jsonify(get_stats(conn, _load_preferred_companies()))
    finally:
        conn.close()


@app.route("/api/jobs")
def api_jobs():
    category = request.args.get("category", "recent")
    conn = get_db()
    try:
        preferred = _load_preferred_companies() if category == "preferred" else None
        jobs = get_jobs(conn, category, preferred)
        loc_pri = _load_location_priority()
        default_pri = len(loc_pri) + 1
        jobs.sort(key=lambda j: _location_sort_key(j.get("location", ""), loc_pri, default_pri))
        return jsonify([
            {
                "id": j["id"],
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "salary_min": j["salary_min"],
                "salary_max": j["salary_max"],
                "salary_currency": j["salary_currency"],
                "salary_period": j["salary_period"],
                "min_experience": j["min_experience"],
                "site": j["site"],
                "is_saved": bool(j["is_saved"]),
                "date_posted": j["date_posted"],
            }
            for j in jobs
        ])
    finally:
        conn.close()


def _location_sort_key(location, loc_pri, default):
    if not location:
        return default
    loc_lower = location.lower()
    for name, priority in loc_pri.items():
        if name.lower() in loc_lower:
            return priority
    return default


@app.route("/api/jobs/<int:job_id>")
def api_job(job_id):
    conn = get_db()
    try:
        job = get_job(conn, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job)
    finally:
        conn.close()


@app.route("/api/jobs/<int:job_id>/save", methods=["POST"])
def api_save(job_id):
    conn = get_db()
    try:
        save_job(conn, job_id)
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/jobs/<int:job_id>/unsave", methods=["POST"])
def api_unsave(job_id):
    conn = get_db()
    try:
        unsave_job(conn, job_id)
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    from datetime import date
    from scripts.scrape import scrape_iter

    _scrape_stop.clear()
    _scrape_logger.info("Scrape started")

    def generate():
        conn = get_db()
        init_db(conn)
        batch_id = date.today().isoformat()
        total_new = 0

        try:
            for event in scrape_iter(stop_event=_scrape_stop):
                etype = event["type"]

                if etype == "error":
                    _scrape_logger.error(
                        "Search failed: '%s' in '%s' — %s",
                        event["term"], event["location"], event["message"],
                    )

                if etype == "result" and event.get("dataframe") is not None:
                    batch_df = event.pop("dataframe")
                    count_before = conn.execute(
                        "SELECT COUNT(*) AS c FROM jobs"
                    ).fetchone()["c"]
                    store_jobs(conn, batch_df, batch_id)
                    count_after = conn.execute(
                        "SELECT COUNT(*) AS c FROM jobs"
                    ).fetchone()["c"]
                    batch_new = count_after - count_before
                    total_new += batch_new
                    event["stored"] = batch_new
                    _scrape_logger.info(
                        "Stored '%s' in '%s': %d jobs (%d new)",
                        event["term"], event["location"],
                        event["count"], batch_new,
                    )

                if etype == "done":
                    event["new_jobs"] = total_new
                    _scrape_logger.info(
                        "Scrape complete: %d total, %d new",
                        event["total"], total_new,
                    )

                yield "data: " + json.dumps(event) + "\n\n"

        except GeneratorExit:
            _scrape_logger.info("Scrape stream closed by client")
        except Exception as e:
            _scrape_logger.error("Scrape crashed: %s", e)
            yield "data: " + json.dumps({
                "type": "fatal", "message": str(e)
            }) + "\n\n"
        finally:
            conn.close()

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/scrape/stop", methods=["POST"])
def api_scrape_stop():
    _scrape_stop.set()
    _scrape_logger.info("Scrape stop requested")
    return jsonify({"ok": True})


@app.route("/api/jobs/<int:job_id>/match", methods=["POST"])
def api_match(job_id):
    conn = get_db()
    try:
        job = get_job(conn, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

        result = match_job(job)
        store_match(conn, job_id, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Starting JobScrape server at http://localhost:5000")
    app.run(debug=True, port=5000)
