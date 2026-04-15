# Contributing to AI Job Agent

## Local Setup

**Requirements:** Python 3.11+, Google Chrome

1. **Clone and install dependencies**
   ```bash
   git clone https://github.com/your-username/ai-job-agent.git
   cd ai-job-agent
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys:
   #   OPENAI_API_KEY  — required (resume embeddings)
   #   GROQ_API_KEY    — recommended (free LLM via groq.com)
   #   HUNTER_API_KEY  — optional (recruiter email finder)
   ```

3. **Start the backend**
   ```bash
   uvicorn backend.main:app --reload
   # Runs at http://localhost:8000
   # Dashboard: http://localhost:8000/dashboard
   ```

4. **Upload a resume**
   ```bash
   curl -X POST http://localhost:8000/api/resumes/upload \
     -F "file=@/path/to/your/resume.pdf"
   ```

5. **Load the Chrome extension**
   - Open `chrome://extensions`
   - Enable **Developer mode**
   - Click **Load unpacked** and select the `extension/` folder
   - Pin the extension, then set the backend URL to `http://localhost:8000`

6. **Test it** — Navigate to any job posting (LinkedIn, Greenhouse, Lever, Workday) and click the extension icon.

## Project Structure

```
backend/
  agents/         # Job parsing, resume matching, outreach generation, follow-ups
  models/         # Pydantic request/response models
  services/       # Hunter.io contact discovery
  storage/        # SQLite database + ORM models
  utils/          # Logger
  config.py       # All settings (loaded from .env)
  main.py         # FastAPI app + all endpoints
extension/
  popup.html/js   # Chrome extension popup UI
  content.js      # Page scraper injected on job pages
  manifest.json
```

## API Keys

| Key | Where to get | Required? |
|-----|-------------|-----------|
| `OPENAI_API_KEY` | platform.openai.com/api-keys | Yes |
| `GROQ_API_KEY` | console.groq.com | Recommended (free) |
| `HUNTER_API_KEY` | hunter.io/api-keys | Optional |
| `API_KEY` | Set any secret string | Optional (auth for hosted deployments) |

## Submitting Changes

- Keep PRs focused — one feature or fix per PR
- Run the server locally and test the golden path before opening a PR
- The `main` branch is deployed to Render; keep it stable
