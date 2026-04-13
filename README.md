# US Macro Regime Dashboard

Displays the yield curve (T10Y2Y) and 5-year breakeven inflation rate (T5YIE)
from FRED, smoothed with either a moving average or Z-score of rate of change.
Classifies the current US macro regime across four quadrants: Goldilocks,
Inflationary Boom, Stagflation, and Bust/Deflation.

Stack: Python · Flask · Gunicorn · FRED API

---

## Deploy to GitHub + Render

### Step 1 — Create the GitHub repo

1. Go to github.com and sign in
2. Click the **+** icon → **New repository**
3. Name it `Macro-Regime-Dashboard` (or anything you like)
4. Leave it **Public**, no README, no .gitignore → click **Create repository**

### Step 2 — Upload the files

GitHub lets you drag and drop files directly in the browser — no Git needed.

1. On your new repo page, click **uploading an existing file**
2. Drag in these three files from this folder:
   - `app.py`
   - `requirements.txt`
   - `templates/index.html`  ← make sure to upload this into a `templates/` folder

   **To create the templates folder on GitHub:**
   - Click **Add file → Create new file**
   - In the filename box, type `templates/index.html`
   - Paste the contents of `templates/index.html`
   - Click **Commit new file**
   - Then upload `app.py` and `requirements.txt` via drag and drop

3. Commit all files

### Step 3 — Create the Render web service

1. Go to render.com and sign in
2. Click **New → Web Service**
3. Connect your GitHub account if not already connected
4. Select your `Macro-Regime-Dashboard` repo
5. Fill in the settings:

   | Field | Value |
   |---|---|
   | Name | macro-regime-dashboard (or anything) |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn app:app --workers 1 --bind 0.0.0.0:$PORT` |
   | Instance Type | Free |

6. Click **Advanced** → **Add Environment Variable**:
   - Key: `FRED_API_KEY`
   - Value: your FRED API key

7. Click **Create Web Service**

Render will build and deploy automatically. Takes about 2 minutes.

### Step 4 — Set up auto-refresh (optional)

Render's free tier spins down after inactivity. To keep it fresh and awake,
set up a free cron job at cron-job.org:

- URL: `https://your-app-name.onrender.com/api/refresh`
- Schedule: Once daily at 9 PM ET (after FRED updates)

This also forces a cache refresh so the data is always current.

---

## Local development

```bash
pip install flask
export FRED_API_KEY=your_key_here
python app.py
```

Then open http://localhost:5000

---

## How it works

- `/` — serves the dashboard
- `/api/data` — fetches T10Y2Y + T5YIE from FRED, caches for 4 hours, returns JSON
- `/api/refresh` — clears cache and re-fetches (use this for your cron job)

The smoothing and regime calculation all happen in the browser — no server
re-fetch needed when you adjust the window or toggle between SMA and Z-score.
