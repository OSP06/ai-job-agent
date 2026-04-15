# AI Job Agent

> A Chrome extension + self-hosted backend that captures job postings, scores them against your resumes, finds the recruiter's email, and drops a personalised cold email into your Gmail Drafts — in under 30 seconds.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688)
![Chrome](https://img.shields.io/badge/Chrome-Extension-yellow)

---

## What it does

1. **You visit a job posting** on LinkedIn, Greenhouse, Lever, Indeed, Workday, or any job board
2. **Click the extension** — it reads the page automatically
3. **Click "Capture & Process"** — in 15–30 seconds you get:
   - Your best-matching resume selected from all your uploaded resumes
   - A match score (0–100%) — 75%+ means strong fit
   - The recruiter or hiring manager's email via Hunter.io
   - A personalised cold email already in your Gmail Drafts
   - Day-7 and Day-14 follow-up emails scheduled automatically
4. **Review and send** — nothing sends without your approval

---

## How it compares

| Tool | AI matching | Recruiter email | Gmail drafts | Follow-ups | Cost |
|------|-------------|-----------------|--------------|------------|------|
| Teal / Simplify | No | No | No | No | Free |
| LazyApply | Bulk apply only | No | No | No | $40/mo |
| Sonara | Yes | No | No | No | $40/mo |
| **AI Job Agent** | **Yes** | **Yes** | **Yes** | **Yes** | **~$0/mo** |

---

## Running cost

| Setup | What it uses | Monthly cost at 30 jobs/day |
|-------|-------------|----------------------------|
| OpenAI only | GPT-4o + GPT-4o-mini + embeddings | ~$6.80 |
| **Groq + OpenAI** | **Llama-3 (free) + embeddings only** | **~$0.01** |

**Recommended**: set both `GROQ_API_KEY` (free, no card) and `OPENAI_API_KEY` (for embeddings only). This costs essentially nothing. See [AI Provider Setup](#ai-provider-setup) below.

---

## Quick Start — No Code Required

Deploy the backend to Render's free tier in about 10 minutes.

### Step 1 — Fork and deploy to Render

1. Fork this repository to your GitHub account
2. Go to [render.com](https://render.com) and sign up (free)
3. Click **New → Web Service** → connect your forked repo
4. Set **Runtime** to Python, leave build/start commands as-is
5. Add a free PostgreSQL database: **New → PostgreSQL** → copy the Internal Database URL
6. Set environment variables (see Step 2)
7. Click **Deploy**

### Step 2 — Set environment variables in Render

Go to your web service → **Environment** tab. Add the following:

| Variable | Required | Value |
|----------|----------|-------|
| `DATABASE_URL` | Yes | Render PostgreSQL → Internal URL |
| `OPENAI_API_KEY` | Yes | See [AI Provider Setup](#ai-provider-setup) |
| `GROQ_API_KEY` | Recommended | See [AI Provider Setup](#ai-provider-setup) |
| `HUNTER_API_KEY` | Recommended | [hunter.io](https://hunter.io) — free: 25 searches/month |
| `GMAIL_TOKEN_JSON` | Recommended | See [Gmail Setup](#gmail-setup) |
| `GMAIL_SENDER_EMAIL` | Recommended | Your Gmail address |
| `MATCH_SCORE_THRESHOLD` | Optional | Default `0.50` |

### Step 3 — Upload your resumes

Once deployed, go to `https://your-app.onrender.com/docs` and use `POST /api/resumes/upload` to upload your PDF resumes. Upload all versions (general, backend-focused, AI-focused, etc.).

### Step 4 — Install the Chrome extension

1. Download or clone this repo to your computer
2. Open Chrome → `chrome://extensions`
3. Enable **Developer mode** (top-right toggle)
4. Click **Load unpacked** → select the `extension/` folder
5. Pin the extension to your toolbar
6. Click the extension icon → paste your Render URL → Save

You're ready. Visit any job posting and click **Capture & Process**.

---

## AI Provider Setup

The agent uses two AI providers. You can use either or both.

### OpenAI (required for embeddings)

OpenAI is used for resume embeddings (matching your resume to the job). This is required regardless of which LLM provider you choose — Groq has no embedding models.

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Create an API key
3. Add credit — $5 will last years at 30 jobs/day (embeddings cost ~$0.01/month)
4. Set `OPENAI_API_KEY` in your environment

If `GROQ_API_KEY` is not set, OpenAI also handles job parsing (GPT-4o) and outreach generation (GPT-4o-mini).

### Groq (recommended — free LLM tier)

Groq runs Llama-3 at no cost with no credit card required. When set, it handles job parsing and outreach generation, leaving OpenAI only for embeddings.

1. Go to [console.groq.com](https://console.groq.com) and sign up (free)
2. Create an API key
3. Set `GROQ_API_KEY` in your environment

**Routing logic:**
- `GROQ_API_KEY` set → Groq handles job parsing + outreach (Llama-3)
- `GROQ_API_KEY` not set → OpenAI handles everything
- Both keys set → Groq for LLM, OpenAI for embeddings (recommended)

---

## Gmail Setup

Gmail drafts require a one-time OAuth2 setup on your local machine.

**Prerequisites:** Python installed locally and a Google Cloud project.

1. Go to [Google Cloud Console](https://console.cloud.google.com) → create a project
2. Enable the **Gmail API**
3. Create **OAuth2 credentials** → Desktop App → download `credentials.json`
4. Place `credentials.json` in the `backend/` folder
5. Run:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
   python scripts/gmail_auth.py
   ```
6. A browser window opens → sign in → grant permission
7. Copy the contents of the generated `backend/token.json`
8. In Render → Environment → add `GMAIL_TOKEN_JSON` → paste the entire JSON

---

## Local Development

### Prerequisites
- Python 3.12+
- An OpenAI API key (and optionally a Groq API key)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/ai-job-agent.git
cd ai-job-agent

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY and optionally GROQ_API_KEY

# 5. Start the backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 6. Upload a resume
curl -X POST http://localhost:8000/api/resumes/upload \
  -F "file=@/path/to/your/resume.pdf"
```

Load the Chrome extension pointing to `http://localhost:8000`.

### Running tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Using the Extension

### Processing a job

1. Navigate to any job posting
2. Click the AI Job Agent icon in your toolbar
3. Wait for "Ready to process" (green status)
4. Click **Capture & Process**
5. In 15–30 seconds you'll see:
   - Match score and which resume was selected
   - Matched and missing skills
   - Outreach email — click "View email" to expand
   - Gmail draft link — click to open directly in Gmail Drafts
   - Contacts found — click LinkedIn icons to open profiles
6. After submitting your application, click **Mark as Applied** to start the Day-7 / Day-14 follow-up countdown

### Match score guide

| Score | Meaning |
|-------|---------|
| 75–100% | Strong match — apply with confidence |
| 55–75% | Good match — worth applying, minor gaps |
| 40–55% | Partial match — gaps are visible |
| < 40% | Weak match — significant mismatch |

### Duplicate detection

If you try to process a job you've already captured, the extension shows "Already captured — Application #N" instead of running the pipeline again.

### Short page text warning

If you see "Short page text (N chars) — scroll down or wait, then re-scan", the page is JavaScript-rendered and hasn't fully loaded. Scroll to the bottom, wait 2–3 seconds, then click **Re-scan page**.

---

## Application Dashboard

Visit `https://your-app.onrender.com/dashboard` to track all applications.

- Update status via dropdown (captured → applied → interviewing → offer / rejected)
- Export full history as CSV
- View which skills appear most often in jobs you're missing — fix your resume

---

## Architecture

```
Chrome Extension (popup.js + content.js)
         │
         │  POST /api/jobs/process
         ▼
   FastAPI Backend
         │
         ├─ job_parser.py        → Groq Llama-3.3-70B or GPT-4o
         ├─ resume_matcher.py    → Hybrid score: 0.4×embedding + 0.6×keyword overlap
         ├─ embeddings.py        → OpenAI text-embedding-3-small (always)
         ├─ outreach_generator   → Groq Llama-3.1-8B or GPT-4o-mini
         ├─ recruiter_finder     → Hunter.io: find + verify recruiter email
         ├─ email_service.py     → Creates Gmail Draft via OAuth2
         └─ database.py          → Postgres (Render) / SQLite (local)
```

**Hybrid scoring formula:**
```
hybrid = 0.4 × norm_embedding + 0.6 × keyword_overlap
norm_embedding = clamp((cosine − 0.20) / 0.50, 0, 1)
```

---

## API Reference

Full interactive docs at `https://your-app.onrender.com/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs/process` | Full pipeline — called by the extension |
| `GET` | `/api/applications` | List all applications |
| `PATCH` | `/api/applications/{id}/status` | Update application status |
| `POST` | `/api/applications/{id}/apply` | Mark applied, start follow-up countdown |
| `GET` | `/api/resumes/gaps` | Skill gap report across all jobs |
| `POST` | `/api/resumes/upload` | Upload a PDF resume |
| `GET` | `/api/export/csv` | Download all applications as CSV |
| `GET` | `/dashboard` | HTML application dashboard |
| `GET` | `/health` | Health check |

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required. Used for embeddings; also LLM if no Groq key |
| `GROQ_API_KEY` | — | Optional but recommended. Routes LLM calls to free Groq tier |
| `DATABASE_URL` | SQLite locally | Postgres connection string on Render |
| `HUNTER_API_KEY` | — | Optional. Recruiter email discovery. Free: 25 searches/month |
| `GMAIL_TOKEN_JSON` | — | Optional. Full JSON of token.json for Gmail Drafts |
| `GMAIL_SENDER_EMAIL` | — | Optional. Your Gmail address |
| `MATCH_SCORE_THRESHOLD` | `0.50` | Minimum score to generate outreach email |
| `FOLLOWUP_DAY_1` | `7` | Days after applying to draft first follow-up |
| `FOLLOWUP_DAY_2` | `14` | Days after applying to draft second follow-up |

---

## Supported Job Boards

LinkedIn Jobs · Greenhouse · Lever · Workday · Indeed · Ashby · any site with `<main>` or `<article>`

---

## Contributing

PRs welcome. Good first issues:
- Add more job board selectors to `extension/content.js`
- Add API key authentication to protect backend endpoints
- Add more skills to the vocabulary in `backend/agents/resume_matcher.py`
- Write integration tests for the `/api/jobs/process` pipeline

---

## Privacy

- Resume text and embeddings are stored in **your own** database — not shared
- Job posting text is sent to OpenAI or Groq for parsing (subject to their data policies)
- Only the company domain is sent to Hunter.io — not your personal data
- Gmail credentials never leave your environment

---

## License

MIT — free to use, modify, and distribute.

---

Built with [FastAPI](https://fastapi.tiangolo.com) · [OpenAI](https://openai.com) · [Groq](https://groq.com) · [Hunter.io](https://hunter.io) · Chrome Extensions API
