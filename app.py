import os
import time
import json
import urllib.request
import urllib.error
from flask import Flask, jsonify, render_template, abort

app = Flask(__name__)

# ── Simple in-memory cache (4-hour TTL — FRED data is daily) ─────────────────
_cache = {"data": None, "fetched_at": 0}
CACHE_TTL = 4 * 60 * 60  # 4 hours in seconds

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
START_DATE   = "2019-01-01"

# ── FRED fetch ─────────────────────────────────────────────────────────────────

def fetch_series(series_id):
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY environment variable is not set.")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_API_KEY}"
        f"&observation_start={START_DATE}"
        "&sort_order=asc"
        "&file_type=json"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    if "error_message" in data:
        raise ValueError(f"FRED error: {data['error_message']}")
    return [
        {"date": o["date"], "value": float(o["value"])}
        for o in data["observations"]
        if o["value"] != "."
    ]

def get_data():
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]

    curve = fetch_series("T10Y2Y")
    bei   = fetch_series("T5YIE")

    _cache["data"] = {
        "curve": curve,
        "bei": bei,
        "fetched_at": time.strftime("%B %d, %Y at %H:%M UTC", time.gmtime()),
    }
    _cache["fetched_at"] = now
    return _cache["data"]

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    try:
        return jsonify(get_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"FRED returned HTTP {e.code}. Check your API key."}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {e}"}), 502

@app.route("/api/refresh")
def api_refresh():
    """Force-clear the cache and re-fetch. Call this from cron-job.org."""
    _cache["data"] = None
    _cache["fetched_at"] = 0
    try:
        get_data()
        return jsonify({"status": "ok", "fetched_at": _cache["data"]["fetched_at"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    app.run(debug=True)
