# 🤖 AI Job Agent

> A Chrome extension + self-hosted backend that captures job postings, scores them against your resumes, finds the recruiter's email, and drops a personalised cold email into your Gmail Drafts — in under 30 seconds.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688)
![Chrome](https://img.shields.io/badge/Chrome-Extension-yellow)

---

## What it does

Most job application tools either auto-spam hundreds of applications (bad) or just track what you manually enter (pointless). This does something different:

1. **You visit a job posting** on LinkedIn, Greenhouse, Lever, Indeed, Workday, or any job board
2. **Click the extension** → it reads the job description automatically
3. **Click "Capture & Process"** → in 15–30 seconds you get:
   - Your best-matching resume selected from all your uploaded resumes
   - A hybrid match score (0–100%) calibrated to be meaningful — 75%+ means you're a strong fit
   - The recruiter or hiring manager's email found via Hunter.io
   - A personalised cold email already waiting in your Gmail Drafts
   - Day-7 and Day-14 follow-up emails scheduled automatically
4. **You review the draft** → send if happy, edit if not. Nothing sends automatically.

---

## How it's different from other tools

| Tool | What it does | What's missing |
|------|-------------|----------------|
| **Teal / Simplify** | Job tracking + resume builder | No outreach, no AI matching |
| **LazyApply / Jobright** | Bulk auto-apply | Spray-and-pray, no personalisation |
| **Sonara** (~$40/mo) | AI job search | No recruiter contact discovery |
| **Notion templates** | Manual tracking | Everything |
| **AI Job Agent** | Full pipeline | Nothing — it's all here, free |

**Unique combination this tool offers:**
- Hybrid resume scoring (embedding similarity + keyword overlap) — not just keyword matching
- Hunter.io contact discovery — finds the actual human to email, not the jobs@ inbox
- Gmail Drafts — you approve before sending, not a bot spamming on your behalf
- All three resumes compared — picks the right one per job automatically
- Follow-up cadence built in — Day 7, Day 14, then marks no_response

---

## Features

- **Chrome Extension (Manifest V3)** — works on LinkedIn, Greenhouse, Lever, Workday, Indeed, Ashby, and most ATS platforms
- **Smart resume matching** — upload multiple resumes; the agent picks the best one for each job using semantic embeddings + skill overlap
- **Recruiter discovery** — Hunter.io finds HR, recruiting, and management contacts at the hiring company and verifies their email
- **Outreach generation** — GPT-4o-mini writes a 3–4 sentence personalised cold email based on your resume and the job requirements
- **Gmail Drafts** — email lands in your Gmail Drafts for review before sending
- **Application dashboard** — track every application, update status (captured → applied → interviewing → offer/rejected)
- **Follow-up scheduler** — Day-7 and Day-14 follow-up drafts auto-generated when you mark a job as applied
- **Resume gap report** — aggregates missing skills across all jobs you've processed; tells you what to add to your resume
- **Duplicate detection** — won't reprocess the same job URL twice
- **CSV export** — download your full application history

---

## Architecture

```
Chrome Extension (popup.js + content.js)
         │
         │  POST /api/jobs/process
         ▼
   FastAPI Backend (Render)
         │
         ├─ job_parser.py      → GPT-4o extracts title, company, requirements, domain
         ├─ resume_matcher.py  → Hybrid score: 0.4×embedding + 0.6×keyword overlap
         ├─ outreach_generator → GPT-4o-mini writes cold email
         ├─ recruiter_finder   → Hunter.io: find + verify recruiter email
         ├─ email_service.py   → Creates Gmail Draft via OAuth2
         └─ database.py        → Postgres (Render) / SQLite (local)
```

---

## Quick Start — No Code Required

This route deploys the backend to Render's free tier in about 5 minutes.

### Step 1 — Fork and deploy to Render

1. Fork this repository to your GitHub account
2. Go to [render.com](https://render.com) and sign up (free)
3. Click **New → Web Service** → connect your forked repo
4. Choose **Python** environment, leave the build/start commands as-is
5. Add a free **PostgreSQL** database: New → PostgreSQL → copy the Internal Database URL
6. Set environment variables (see table below)
7. Click **Deploy**

### Step 2 — Set environment variables in Render

Go to your web service → **Environment** tab and add:

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `DATABASE_URL` | Yes | Render PostgreSQL → Internal URL |
| `OPENAI_API_KEY` | Yes | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `HUNTER_API_KEY` | Recommended | [hunter.io](https://hunter.io) — free tier gives 25 searches/month |
| `GMAIL_TOKEN_JSON` | Recommended | See Gmail setup below |
| `GMAIL_SENDER_EMAIL` | Recommended | Your Gmail address |
| `MATCH_SCORE_THRESHOLD` | Optional | Default `0.50` — minimum score to generate outreach |

### Step 3 — Upload your resumes

Once deployed, go to `https://your-app.onrender.com/docs` and use the `POST /api/resumes/upload` endpoint to upload your PDF resumes. Upload all versions (e.g. general, backend-focused, AI-focused).

### Step 4 — Install the Chrome extension

1. Download or clone this repo to your computer
2. Open Chrome → go to `chrome://extensions`
3. Enable **Developer mode** (top right toggle)
4. Click **Load unpacked** → select the `extension/` folder
5. Pin the extension to your toolbar
6. Click the extension icon → paste your Render URL in the Backend field → Save

You're ready. Visit any job posting and click Capture & Process.

---

## Gmail Setup (for draft creation)

Gmail drafts require a one-time OAuth2 setup on your local machine.

**Prerequisites:** Python installed locally, and a Google Cloud project.

1. Go to [Google Cloud Console](https://console.cloud.google.com) → Create a project
2. Enable the **Gmail API**
3. Create OAuth2 credentials → Desktop App → download `credentials.json`
4. Place `credentials.json` in the `backend/` folder
5. Run:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
   python scripts/gmail_auth.py
   ```
6. A browser window opens → sign in → grant permission
7. Copy the contents of the generated `backend/token.json`
8. In Render → Environment → add `GMAIL_TOKEN_JSON` → paste the entire JSON content

---

## Local Development Setup

### Prerequisites
- Python 3.12+
- An OpenAI API key

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
# Edit .env and fill in your API keys

# 5. Start the backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 6. Upload your resumes (in another terminal or via the /docs UI)
curl -X POST http://localhost:8000/api/resumes/upload \
  -F "file=@/path/to/your/resume.pdf"
```

Then load the Chrome extension pointing to `http://localhost:8000`.

---

## Using the Extension

### Processing a job
1. Navigate to any job posting
2. Click the AI Job Agent icon in your toolbar
3. Wait for the page scan (green "Ready to process" status)
4. Click **Capture & Process**
5. In 15–30 seconds you'll see:
   - Match score (green = strong fit, amber = borderline, red = weak)
   - Which of your resumes was selected
   - Outreach status — click "View email ↓" to see the draft
   - Gmail status — click "Created ✓ — Open →" to go directly to Gmail Drafts
   - Contacts found at the company (click to open LinkedIn profiles)
   - Matched and missing skills
6. After you've submitted the actual application, click **Mark as Applied**
   — this starts the Day-7 / Day-14 follow-up countdown

### Understanding the match score
| Score | Meaning |
|-------|---------|
| 75–100% | Strong match — apply with confidence |
| 55–75% | Good match — worth applying, a few skill gaps |
| 40–55% | Partial match — you can apply but gaps are visible |
| < 40% | Weak match — significant skill mismatch |

### Short page text warning
If you see "Short page text (N chars) — scroll down or wait, then re-scan", the job page is JavaScript-rendered and hasn't fully loaded. Scroll to the bottom, wait 2–3 seconds, then click **Re-scan page**.

---

## Application Dashboard

Visit `https://your-app.onrender.com/dashboard` to see all your applications in one place.

- **Update status** — use the dropdown in each row (captured → applied → interviewing → offer / rejected)
- **Export CSV** — download your full application history
- **Resume Gaps** — see which skills appear most often in jobs you're applying for but are missing from all your resumes

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
| `OPENAI_API_KEY` | — | Required. Job parsing, embeddings, and outreach generation |
| `DATABASE_URL` | SQLite locally | Postgres connection string on Render |
| `HUNTER_API_KEY` | — | Optional. Recruiter email discovery. Free: 25 searches/month |
| `GMAIL_TOKEN_JSON` | — | Optional. Full JSON of token.json for Gmail Drafts |
| `GMAIL_SENDER_EMAIL` | — | Optional. Your Gmail address |
| `MATCH_SCORE_THRESHOLD` | `0.50` | Minimum score to generate outreach email |
| `FOLLOWUP_DAY_1` | `7` | Days after applying to draft first follow-up |
| `FOLLOWUP_DAY_2` | `14` | Days after applying to draft second follow-up |
| `NOTION_TOKEN` | — | Optional. Notion integration |
| `NOTION_DATABASE_ID` | — | Optional. Notion database for syncing applications |

---

## Cost Estimate

Running on Render free tier (~20 jobs/week):

| Service | Cost |
|---------|------|
| Render Web Service | Free |
| Render PostgreSQL | Free |
| OpenAI API (parsing + embeddings + outreach) | ~$0.50–$2/month |
| Hunter.io | Free (25 searches/month) |
| **Total** | **~$1–2/month** |

---

## Supported Job Boards

LinkedIn Jobs · Greenhouse · Lever · Workday · Indeed · Ashby · any site with `<main>` or `<article>` (generic fallback)

---

## Contributing

PRs welcome. Good first issues:
- Add tests for the hybrid scoring formula (`backend/agents/resume_matcher.py`)
- Add API key authentication to protect backend endpoints
- Add more job board selectors to `extension/content.js`
- Move the dashboard HTML to a `templates/` directory

---

## Privacy

- Resume text and embeddings are stored in **your own** database — not shared
- Job posting text is sent to OpenAI for parsing (subject to OpenAI's data policy)
- Only the company domain is sent to Hunter.io — not your personal data
- Gmail credentials never leave your environment

---

## License

MIT — free to use, modify, and distribute.

---

Built with [FastAPI](https://fastapi.tiangolo.com) · [OpenAI](https://openai.com) · [Hunter.io](https://hunter.io) · Chrome Extensions API
