# AI Job Application Agent

A local AI agent that captures job postings via a Chrome extension, scores them against your resumes, generates personalized outreach, creates Gmail drafts, and schedules follow-ups — all running on your machine.

---

## How it works

```
Chrome Extension  →  Local FastAPI Backend  →  SQLite DB
      ↓                      ↓
  Scrape page          1. Parse job (GPT-4o)
                        2. Match resume (sentence-transformers)
                        3. Confidence gate (≥70% → proceed)
                        4. Generate outreach (Claude Sonnet)
                        5. Find recruiter (Hunter.io, optional)
                        6. Create Gmail draft
                        7. Schedule follow-ups (Day 7 + Day 14)
```

**Follow-up schedule:**
| Day | Action |
|-----|--------|
| 0 | Capture + outreach draft created |
| 7 | Follow-up #1 draft auto-generated |
| 14 | Follow-up #2 (final) draft created, status → `no_response` |

---

## Project structure

```
ai-job-agent/
├── backend/
│   ├── main.py                  FastAPI app + all endpoints
│   ├── config.py                Pydantic settings from .env
│   ├── models/
│   │   └── job_model.py         Pydantic schemas
│   ├── agents/
│   │   ├── job_parser.py        OpenAI GPT-4o structured extraction
│   │   ├── resume_matcher.py    sentence-transformers cosine similarity
│   │   ├── outreach_generator.py  Claude Sonnet cold email + follow-ups
│   │   ├── recruiter_finder.py  Hunter.io contact lookup
│   │   └── followup_scheduler.py  APScheduler Day-7/14 jobs
│   ├── services/
│   │   ├── email_service.py     Gmail API OAuth2 draft creation
│   │   ├── notion_service.py    Optional Notion sync
│   │   └── hunter_service.py    Re-export of recruiter_finder
│   ├── storage/
│   │   └── database.py          SQLAlchemy + 4-table schema + CRUD
│   ├── resumes/                 ← Put your PDF resumes here
│   └── utils/
│       ├── embeddings.py        sentence-transformers singleton
│       └── logger.py            loguru structured logging
├── extension/
│   ├── manifest.json            Chrome Manifest V3
│   ├── content.js               Job page scraper
│   ├── popup.html               Extension UI
│   └── popup.js                 Extension logic
├── scripts/
│   ├── setup_env.sh             First-time setup
│   └── run_agent.sh             Start the backend
├── .env.example                 Environment variable template
└── requirements.txt
```

---

## Database schema

| Table | Description |
|-------|-------------|
| `applications` | One row per job captured |
| `contacts` | Recruiter/hiring-manager contacts per application |
| `outreach_messages` | Initial cold email drafts |
| `followups` | Day-7 and Day-14 follow-up drafts |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/ai-job-agent
cd ai-job-agent
./scripts/setup_env.sh
```

### 2. Add your API keys to `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-...    # Required — Claude Sonnet for outreach
OPENAI_API_KEY=sk-...           # Required — GPT-4o for job parsing
HUNTER_API_KEY=...              # Optional — recruiter email lookup
NOTION_TOKEN=...                # Optional — Notion database sync
```

### 3. Add your resumes

Drop PDF files into `backend/resumes/`. Name them descriptively:
```
backend/resumes/
  backend_resume.pdf
  ai_ml_resume.pdf
  cloud_resume.pdf
```

The agent automatically picks the best-matching resume per job.

### 4. Gmail setup (optional but recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable Gmail API
3. Create OAuth2 credentials (Desktop app) → Download `credentials.json`
4. Place `credentials.json` at `backend/credentials.json`
5. First run will open a browser for OAuth consent

### 5. Start the backend

```bash
./scripts/run_agent.sh
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Chrome Extension

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `extension/` folder
4. Navigate to any job posting and click the extension icon

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs/process` | Full pipeline (called by extension) |
| `GET` | `/api/applications` | List applications (`?status=applied`) |
| `GET` | `/api/applications/{id}` | Application detail with outreach + contacts |
| `PATCH` | `/api/applications/{id}/status` | Update status |
| `POST` | `/api/applications/{id}/apply` | Mark applied, set follow-up dates |
| `GET` | `/api/followups/pending` | List overdue follow-ups |
| `POST` | `/api/followups/{id}/process` | Manually generate follow-up |
| `GET` | `/api/export/csv` | Download all applications as CSV |
| `GET` | `/health` | Health check |

---

## Match score threshold

The agent gates outreach on match score. Default: **70%**.

```
match_score ≥ 70%  →  generate outreach + Gmail draft
match_score < 70%  →  save application, skip outreach
```

Adjust in `.env`:
```
MATCH_SCORE_THRESHOLD=0.65
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| Job parsing | OpenAI GPT-4o (JSON mode) |
| Resume matching | sentence-transformers `all-MiniLM-L6-v2` |
| Outreach | Anthropic Claude Sonnet (`claude-sonnet-4-6`) |
| Scheduler | APScheduler |
| Database | SQLite via SQLAlchemy |
| Email | Gmail API (OAuth2) |
| Extension | Chrome Manifest V3 |
