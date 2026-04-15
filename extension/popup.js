/**
 * popup.js — AI Job Agent
 */

const DEFAULT_BACKEND = "https://ai-job-agent-8zrr.onrender.com";

// ─── State ────────────────────────────────────────────────────────────────────
let scrapedData = null;
let backendUrl  = DEFAULT_BACKEND;

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const jobCard         = document.getElementById("jobCard");
const jobTitle        = document.getElementById("jobTitle");
const jobCompany      = document.getElementById("jobCompany");
const jobUrl          = document.getElementById("jobUrl");
const statusBadge     = document.getElementById("statusBadge");
const statusText      = document.getElementById("statusText");
const processBtn      = document.getElementById("processBtn");
const refreshBtn      = document.getElementById("refreshBtn");
const resultBox       = document.getElementById("resultBox");
const resScore        = document.getElementById("resScore");
const resResume       = document.getElementById("resResume");
const resOutreach     = document.getElementById("resOutreach");
const resDraft        = document.getElementById("resDraft");
const resAppLink      = document.getElementById("resAppLink");
const scoresDivider   = document.getElementById("scoresDivider");
const scoresSection   = document.getElementById("scoresSection");
const scoresBars      = document.getElementById("scoresBars");
const contactRow      = document.getElementById("contactRow");
const resContact      = document.getElementById("resContact");
const backendUrlInput = document.getElementById("backendUrlInput");
const saveUrlBtn      = document.getElementById("saveUrlBtn");
const skillsDivider   = document.getElementById("skillsDivider");
const skillsSection   = document.getElementById("skillsSection");
const matchedSection  = document.getElementById("matchedSection");
const missingSection  = document.getElementById("missingSection");
const matchedPills    = document.getElementById("matchedPills");
const missingPills    = document.getElementById("missingPills");

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  chrome.storage.local.get(["backendUrl"], (result) => {
    backendUrl = result.backendUrl || DEFAULT_BACKEND;
    backendUrlInput.value = backendUrl;
    scrapeCurrentTab();
  });

  processBtn.addEventListener("click", handleProcess);

  refreshBtn.addEventListener("click", () => {
    resetResult();
    scrapeCurrentTab();
  });

  saveUrlBtn.addEventListener("click", () => {
    const val = backendUrlInput.value.trim().replace(/\/$/, "");
    if (!val) return;
    backendUrl = val;
    chrome.storage.local.set({ backendUrl: val }, () => {
      saveUrlBtn.textContent = "Saved ✓";
      setTimeout(() => { saveUrlBtn.textContent = "Save"; }, 1500);
    });
  });

  document.getElementById("docsLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: `${backendUrl}/docs` });
  });

  document.getElementById("appsLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: `${backendUrl}/api/applications` });
  });
});

// ─── Scrape ───────────────────────────────────────────────────────────────────
async function scrapeCurrentTab() {
  setStatus("scraping", "Scanning page…");
  processBtn.disabled = true;
  scrapedData = null;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });

    const response = await chrome.tabs.sendMessage(tab.id, { action: "scrape_job" });
    if (!response || !response.success) throw new Error(response?.error || "Scrape failed");

    scrapedData = response.data;
    displayPreview(scrapedData, tab);

    const textLen = (scrapedData.raw_text || "").length;
    if (textLen < 500) {
      setStatus("scraping", `Short page text (${textLen} chars) — scroll down or wait, then re-scan`);
    } else {
      setStatus("idle", "Ready to process");
    }
    processBtn.disabled = false;

  } catch (err) {
    setStatus("error", `Scan failed: ${err.message}`);
    jobTitle.textContent = "Could not read page";
    jobCard.classList.add("empty");
  }
}

function displayPreview(data, tab) {
  jobCard.classList.remove("empty");
  const parts = (tab.title || "").split(/[-|–—@·]/);
  jobTitle.textContent  = parts[0]?.trim() || "Job Posting";
  jobCompany.textContent = parts[1]?.trim() || "";
  jobUrl.textContent    = data.url;
}

// ─── Process ──────────────────────────────────────────────────────────────────
async function handleProcess() {
  if (!scrapedData) return;

  setStatus("processing", "Processing… (10–30s)");
  processBtn.disabled  = true;
  refreshBtn.disabled  = true;
  resetResult();

  try {
    const resp = await fetch(`${backendUrl}/api/jobs/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scrapedData),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    displayResult(result);
    setStatus("success", "Done ✓");

  } catch (err) {
    setStatus("error", `Error: ${err.message}`);
  } finally {
    processBtn.disabled = false;
    refreshBtn.disabled = false;
  }
}

// ─── Display result ───────────────────────────────────────────────────────────
function displayResult(result) {
  const score    = result.match_score;
  const scorePct = pct(score);

  // Determine threshold from the skip reason if available, else assume 0.9
  const threshold = parseThreshold(result.outreach_skipped_reason) ?? 0.9;

  // Score pill with colour based on real threshold
  resScore.textContent = scorePct;
  resScore.className   = "value " + scoreClass(score, threshold);

  // Resume used
  resResume.textContent = result.resume_used || "—";

  // Outreach
  if (result.outreach_generated) {
    resOutreach.textContent  = "Generated ✓";
    resOutreach.style.color  = "#4caf50";
  } else {
    resOutreach.textContent = result.outreach_skipped_reason || `Skipped (${scorePct})`;
    resOutreach.style.color = "#888";
  }

  // Gmail draft
  resDraft.textContent = result.gmail_draft_id ? "Created ✓" : "Not created";
  resDraft.style.color = result.gmail_draft_id ? "#4caf50" : "#666";

  // Application link
  if (result.application_id) {
    resAppLink.textContent = `#${result.application_id} — view →`;
    resAppLink.onclick = () => chrome.tabs.create({
      url: `${backendUrl}/api/applications/${result.application_id}`,
    });
  }

  // Update job card with parsed data
  jobCard.classList.remove("empty");
  if (result.job_title) jobTitle.textContent  = result.job_title;
  if (result.company)   jobCompany.textContent = result.company;

  // Contact found
  const contacts = result.contacts_found || [];
  contactRow.style.display = "";
  if (contacts.length) {
    const best = contacts[0];
    const verified = best.verified ? " ✓" : "";
    const label = [best.name, best.title].filter(Boolean).join(" · ");
    resContact.textContent = (label || best.email || "—") + verified;
    resContact.style.color = best.verified ? "#4caf50" : "#aaa";
    if (best.linkedin_url) {
      resContact.classList.add("link");
      resContact.onclick = () => chrome.tabs.create({ url: best.linkedin_url });
    }
  } else {
    resContact.textContent = "None found — check HUNTER_API_KEY";
    resContact.style.color = "#555";
  }

  // Matched / missing skill pills
  const matched = result.matched_skills || [];
  const missing = result.missing_skills || [];
  if (matched.length || missing.length) {
    skillsDivider.style.display = "";
    skillsSection.style.display = "";
    if (matched.length) {
      matchedSection.style.display = "";
      matchedPills.innerHTML = matched.slice(0, 8)
        .map(s => `<span class="pill match">${s}</span>`).join("");
    }
    if (missing.length) {
      missingSection.style.display = "";
      missingPills.innerHTML = missing.slice(0, 6)
        .map(s => `<span class="pill missing">${s}</span>`).join("");
    }
  }

  // All resume scores breakdown
  const allScores = result.all_resume_scores || {};
  const names = Object.keys(allScores);
  if (names.length > 1) {
    scoresDivider.style.display = "";
    scoresSection.style.display = "";
    scoresBars.innerHTML = "";

    const maxScore = Math.max(...Object.values(allScores), 0.01);

    // Sort descending
    names.sort((a, b) => allScores[b] - allScores[a]);

    names.forEach((name) => {
      const s     = allScores[name];
      const isBest = name === result.resume_used;
      const barPct  = Math.round((s / maxScore) * 100);
      const fillCls = isBest
        ? (s >= threshold ? "bar-fill best" : "bar-fill low")
        : "bar-fill";

      scoresBars.innerHTML += `
        <div class="score-bar-row">
          <span class="sname ${isBest ? "best" : ""}">${name}</span>
          <div class="bar-track"><div class="${fillCls}" style="width:${barPct}%"></div></div>
          <span class="spct">${pct(s)}</span>
        </div>`;
    });
  }

  resultBox.classList.add("visible");
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function pct(v) { return `${(v * 100).toFixed(0)}%`; }

function scoreClass(score, threshold) {
  if (score >= threshold)        return "score-high";
  if (score >= threshold * 0.75) return "score-mid";
  return "score-low";
}

function parseThreshold(reason) {
  if (!reason) return null;
  const m = reason.match(/threshold\s+([\d.]+)%/i);
  return m ? parseFloat(m[1]) / 100 : null;
}

function setStatus(type, text) {
  statusBadge.className = `badge ${type}`;
  statusText.textContent = text;
  const dot = statusBadge.querySelector(".dot");
  if (dot) dot.classList.toggle("pulse", type === "processing" || type === "scraping");
}

function resetResult() {
  resultBox.classList.remove("visible");
  skillsDivider.style.display = "none";
  skillsSection.style.display = "none";
  matchedSection.style.display = "none";
  missingSection.style.display = "none";
  matchedPills.innerHTML = "";
  missingPills.innerHTML = "";
  scoresDivider.style.display = "none";
  scoresSection.style.display = "none";
  scoresBars.innerHTML = "";
  [resScore, resResume, resOutreach, resDraft].forEach((el) => {
    el.textContent = "—";
    el.className   = "value";
    el.style.color = "";
  });
  resAppLink.textContent = "—";
  resAppLink.onclick     = null;
  contactRow.style.display = "none";
  resContact.textContent   = "—";
  resContact.style.color   = "";
  resContact.classList.remove("link");
  resContact.onclick = null;
}
