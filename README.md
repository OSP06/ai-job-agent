# AI Job Agent

> A Chrome extension + self-hosted backend that captures job postings, scores them against your resumes, finds the recruiter's email, and writes a personalised cold outreach email — in under 30 seconds.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-009688)
![Chrome](https://img.shields.io/badge/Chrome-Extension-yellow)


---

## What it does

1. **Visit any job posting** on LinkedIn, Greenhouse, Lever, Workday, Indeed, or any job board
2. **Click the extension** — it reads the page automatically
3. **Click "Capture & Process"** — in 15–30 seconds you get:
   - Your best-matching resume selected from all your uploaded resumes
   - A match score (0–100%) with matched and missing skills
   - The recruiter or hiring manager's email via Hunter.io
   - A personalised cold outreach email ready to copy and send
   - Day-7 and Day-14 follow-up emails scheduled automatically
4. **Review and send** — nothing is sent without your approval

---

## How it compares

| Tool | AI resume matching | Recruiter email | Outreach email | Follow-ups | Cost |
|------|--------------------|-----------------|----------------|------------|------|
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

**Recommended:** set both `GROQ_API_KEY` (free, no card) and `OPENAI_API_KEY` (embeddings only). Costs essentially nothing.

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

Go to your web service → **Environment** tab:

| Variable | Required | Where to get it |
|----------|----------|-----------------|
| `DATABASE_URL` | Yes | Render PostgreSQL → Internal URL |
| `OPENAI_API_KEY` | Yes | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GROQ_API_KEY` | Recommended | [console.groq.com](https://console.groq.com) — free |
| `HUNTER_API_KEY` | Recommended | [hunter.io](https://hunter.io) — free: 25 searches/month |
| `MATCH_SCORE_THRESHOLD` | Optional | Default `0.50` (0–1 range) |

### Step 3 — Upload your resumes

Once deployed, open `https://your-app.onrender.com/dashboard` and click **⬆ Upload Resume** in the top-right. Upload all your resume versions (general, backend-focused, AI-focused, etc.).

### Step 4 — Install the Chrome extension

1. Download or clone this repo to your computer
2. Open Chrome → `chrome://extensions`
3. Enable **Developer mode** (top-right toggle)
4. Click **Load unpacked** → select the `extension/` folder
5. Pin the extension to your toolbar
6. Click the extension icon → paste your Render URL into the **Backend** field → Save

You're ready. Visit any job posting and click **Capture & Process**.

---

## AI Provider Setup

### OpenAI (required for embeddings)

Used to embed resumes and job descriptions for similarity matching. Required even if you use Groq for the LLM — Groq has no embedding models.

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → create a key
2. Add $5 credit — will last years at 30 jobs/day (embeddings cost ~$0.01/month)
3. Set `OPENAI_API_KEY`

### Groq (recommended — free LLM)

Runs Llama-3 for job parsing and outreach generation at no cost, no credit card required. When set, OpenAI is used only for embeddings.

1. Go to [console.groq.com](https://console.groq.com) → sign up → create a key
2. Set `GROQ_API_KEY`

**Routing logic:**
- Both keys set → Groq for LLM, OpenAI for embeddings (**recommended**)
- Only OpenAI → OpenAI handles everything (~$6.80/month at 30 jobs/day)
- Only Groq → won't work (no embeddings)

---

## Local Development

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ai-job-agent.git
cd ai-job-agent

# 2. Virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — add OPENAI_API_KEY and optionally GROQ_API_KEY

# 5. Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/dashboard` to upload resumes, and load the extension pointing at `http://localhost:8000`.

---

## Using the Extension

### Processing a job

1. Navigate to any job posting
2. Click the AI Job Agent icon in your toolbar
3. Wait for "Ready to process" (green status)
4. Click **Capture & Process**
5. In 15–30 seconds you'll see:
   - Match score + which resume was selected
   - Matched and missing skills
   - Outreach email — click "View email" to expand and copy
   - Contacts found with LinkedIn links
6. Click **Mark as Applied** after submitting — starts the Day-7 / Day-14 follow-up countdown

### Uploading resumes from the popup

Click **⬆ Upload resume PDF** at the bottom of the extension popup to upload directly without opening the dashboard.

### Match score guide

| Score | Meaning |
|-------|---------|
| 75–100% | Strong match — apply with confidence |
| 55–75% | Good match — worth applying |
| 40–55% | Partial match — visible gaps |
| < 40% | Weak match — significant mismatch |

### Duplicate detection

If you try to process a job you've already captured, the extension shows "Already captured — Application #N" instead of running the pipeline again.

---

## Application Dashboard

Open `https://your-app.onrender.com/dashboard` to track all applications:

- Upload resumes via the **⬆ Upload Resume** button
- Update status via dropdown (captured → applied → interviewing → offer / rejected)
- Filter by status with the chip strip
- Export full history as CSV
- View skill gaps — skills appearing most in jobs you're missing

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
         ├─ embeddings.py        → OpenAI text-embedding-3-small
         ├─ outreach_generator   → Groq Llama-3.1-8B or GPT-4o-mini
         ├─ recruiter_finder     → Hunter.io: find + verify recruiter email
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
| `POST` | `/api/resumes/upload` | Upload a PDF resume |
| `GET` | `/api/resumes` | List uploaded resumes |
| `GET` | `/api/resumes/gaps` | Skill gap report across all jobs |
| `GET` | `/api/export/csv` | Download all applications as CSV |
| `GET` | `/dashboard` | HTML application dashboard |
| `GET` | `/health` | Health check |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required. Embeddings (+ LLM if no Groq key) |
| `GROQ_API_KEY` | — | Recommended. Free LLM via Groq (Llama-3) |
| `DATABASE_URL` | SQLite locally | Postgres connection string on Render |
| `HUNTER_API_KEY` | — | Optional. Recruiter email finder. Free: 25/month |
| `API_KEY` | — | Optional. Secret to protect write endpoints |
| `MATCH_SCORE_THRESHOLD` | `0.50` | Min score to generate outreach (0–1) |
| `FOLLOWUP_DAY_1` | `7` | Days after applying to draft first follow-up |
| `FOLLOWUP_DAY_2` | `14` | Days after applying to draft final follow-up |
| `SCHEDULER_TIMEZONE` | `America/New_York` | Timezone for follow-up scheduler |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Supported Job Boards

LinkedIn · Greenhouse · Lever · Workday · Indeed · Ashby · any site with `<main>` or `<article>` content

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

Good first issues:
- Add more job board selectors to `extension/content.js`
- Add more skills to the vocabulary in `backend/agents/resume_matcher.py`
- Write integration tests for the `/api/jobs/process` pipeline

---

## Privacy

- Resume text and embeddings are stored in **your own** database — not shared with anyone
- Job posting text is sent to OpenAI or Groq for parsing (subject to their data policies)
- Only the company domain is sent to Hunter.io — not your personal data

---

## License

MIT — free to use, modify, and distribute.

---

Built with [FastAPI](https://fastapi.tiangolo.com) · [OpenAI](https://openai.com) · [Groq](https://groq.com) · [Hunter.io](https://hunter.io) · Chrome Extensions API
