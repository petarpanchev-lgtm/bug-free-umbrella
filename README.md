# Kullamagi Breakout Score — Web App

A Streamlit web app version of the Kullamagi/Qullamaggie breakout scoring tool.
Enter a ticker, get a 0-100 fit score plus a breakdown. See the main
`Kullamagi_Trading_Playbook.docx` for the full rule set this is based on.

Files in this folder:
- `app.py` — the Streamlit UI
- `kullamagi_score.py` — the scoring logic (same as the standalone CLI script)
- `requirements.txt` — dependencies

## Run it locally first (optional, to confirm it works)

```bash
pip install -r requirements.txt
streamlit run app.py
```

It'll open at `http://localhost:8501`.

## Deploy it publicly — Streamlit Community Cloud (free, recommended)

This is the easiest way to get a public URL you can share with anyone. No
server management, no credit card, free for public apps.

1. **Create a GitHub repo** (if you don't already have one for this).
   - Go to github.com → New repository → name it e.g. `kullamagi-score` →
     Create.
   - Upload the three files in this folder (`app.py`, `kullamagi_score.py`,
     `requirements.txt`) via the GitHub web UI ("Add file" → "Upload files"),
     or push them with git:
     ```bash
     cd kullamagi-web
     git init
     git add app.py kullamagi_score.py requirements.txt
     git commit -m "Kullamagi breakout score app"
     git branch -M main
     git remote add origin https://github.com/<your-username>/kullamagi-score.git
     git push -u origin main
     ```

2. **Sign up / log in to Streamlit Community Cloud.**
   - Go to https://share.streamlit.io
   - Sign in with your GitHub account (this also authorizes Streamlit to
     read your repos).

3. **Deploy the app.**
   - Click "New app" (or "Create app").
   - Pick the repo (`kullamagi-score`), branch (`main`), and main file path
     (`app.py`).
   - Click "Deploy". First build takes 1-2 minutes.

4. **You'll get a public URL**, something like:
   `https://kullamagi-score-<random>.streamlit.app`
   Share that link with anyone — it runs the same scoring logic, live,
   against real Yahoo Finance data.

5. **Updating it later:** just push new commits to the GitHub repo — the
   Streamlit app redeploys automatically.

### Notes / limits
- Community Cloud apps "sleep" after a period of inactivity and take a few
  seconds to wake up on the next visit — normal for the free tier.
- Data comes from `yfinance` (Yahoo Finance), which is free and unauthenticated
  but can occasionally rate-limit heavy traffic — fine for personal/shared use.
- If you'd rather not use GitHub/Streamlit Cloud, the same `app.py` runs on
  any host that supports Python web apps (Render, Railway, Fly.io, etc.) —
  the command to run is `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

## Disclaimer
Educational tool only, not financial advice. Not affiliated with or endorsed
by Kristjan Kullamagi / Qullamaggie.
