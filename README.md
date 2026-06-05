# AI SQL Assistant

Convert plain English into SQL and run it against a sample SQLite database.
Powered by Google Gemini. Only read-only `SELECT` queries are allowed.

> Example: _"show top 5 customers by revenue"_ → generated SQL → live results table.

## Project structure

```
ai-sql-assistant/
├── app.py              # Flask website
├── core/
│   ├── nl2sql.py       # English -> SQL (shared core, reused by Phase 2 extension)
│   └── db.py           # SQLite setup, schema, query runner
├── templates/index.html
├── static/ (style.css, app.js)
├── data/shop.db        # auto-created on first run
├── requirements.txt
├── .env.example
└── Procfile            # for hosting (Render/Railway)
```

## Run locally

1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Add your Gemini API key (free at https://aistudio.google.com/app/apikey):
   ```powershell
   copy .env.example .env
   # then edit .env and paste your key
   ```
4. Start the app:
   ```powershell
   python app.py
   ```
5. Open http://127.0.0.1:5000

## Deploy for free

- **Render** (recommended): push to GitHub → New Web Service → build `pip install -r requirements.txt`, start `gunicorn app:app`. Add `GEMINI_API_KEY` as an environment variable.
- **Hugging Face Spaces** / **Railway** also work with the same `Procfile`.

## Safety

`core/nl2sql.py` blocks anything that is not a single `SELECT` statement
(no `INSERT`, `UPDATE`, `DELETE`, `DROP`, stacked queries, etc.).

## Free tier limits

Gemini's free tier has **very strict quotas**:

- ~500 requests per day per API key
- ~2 requests per minute (shared rate limit)

If you hit quota limits, you'll see: _"Free tier quota exhausted"_

**Solutions:**

- Wait a few minutes for the rate limit to reset
- Upgrade to a paid tier at https://aistudio.google.com (even $1/month increases quota significantly)
- Monitor usage at https://ai.dev/rate-limit

For serious use, consider switching to OpenAI's API or another LLM provider.

## Phase 2 (planned)

A VS Code extension will call the same `core` logic via an HTTP endpoint,
with a download link published on this website.
