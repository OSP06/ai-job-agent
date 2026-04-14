/**
 * popup.js — AI Job Agent
 * ────────────────────────
 * Orchestrates the Chrome extension popup:
 *   1. On open: inject content.js and scrape the active tab
 *   2. Display job title/company preview
 *   3. On "Capture & Process": POST to backend, show results
 */

const DEFAULT_BACKEND = "http://localhost:8000";

// ─── State ───────────────────────────────────────────────────────────────────
let scrapedData = null;
let backendUrl = DEFAULT_BACKEND;

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const jobCard          = document.getElementById("jobCard");
const jobTitle         = document.getElementById("jobTitle");
const jobCompany       = document.getElementById("jobCompany");
const jobUrl           = document.getElementById("jobUrl");
const statusBadge      = document.getElementById("statusBadge");
const statusText       = document.getElementById("statusText");
const processBtn       = document.getElementById("processBtn");
const refreshBtn       = document.getElementById("refreshBtn");
const resultBox        = document.getElementById("resultBox");
const resScore         = document.getElementById("resScore");
const resResume        = document.getElementById("resResume");
const resOutreach      = document.getElementById("resOutreach");
const resDraft         = document.getElementById("resDraft");
const backendUrlInput  = document.getElementById("backendUrlInput");
const saveUrlBtn       = document.getElementById("saveUrlBtn");

// ─── On popup open ────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Load saved backend URL
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
});

// ─── Scrape ───────────────────────────────────────────────────────────────────
async function scrapeCurrentTab() {
  setStatus("scraping", "Scanning page…");
  processBtn.disabled = true;
  scrapedData = null;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Inject content script (safe to call even if already injected)
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });

    const response = await chrome.tabs.sendMessage(tab.id, { action: "scrape_job" });

    if (!response || !response.success) {
      throw new Error(response?.error || "Scrape failed");
    }

    scrapedData = response.data;
    displayPreview(scrapedData, tab);
    setStatus("idle", "Ready to process");
    processBtn.disabled = false;

  } catch (err) {
    setStatus("error", `Scan failed: ${err.message}`);
    jobTitle.textContent = "Could not read page";
    jobCard.classList.add("empty");
  }
}

function displayPreview(data, tab) {
  jobCard.classList.remove("empty");

  // Try to extract title/company from page title heuristic
  const parts = (tab.title || "").split(/[-|–—@·]/);
  jobTitle.textContent = parts[0]?.trim() || "Job Posting";
  jobCompany.textContent = parts[1]?.trim() || "";
  jobUrl.textContent = data.url;
}

// ─── Process ──────────────────────────────────────────────────────────────────
async function handleProcess() {
  if (!scrapedData) return;

  setStatus("processing", "Processing… (10–30s)");
  processBtn.disabled = true;
  refreshBtn.disabled = true;
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

function displayResult(result) {
  const score = result.match_score;
  const scorePct = `${(score * 100).toFixed(0)}%`;

  resScore.textContent = scorePct;
  resScore.className = "value " + (score >= 0.7 ? "score-high" : "score-low");

  resResume.textContent = result.resume_used || "—";

  if (result.outreach_generated) {
    resOutreach.textContent = "Generated ✓";
    resOutreach.style.color = "#4caf50";
  } else {
    resOutreach.textContent = `Skipped (${scorePct} < 70%)`;
    resOutreach.style.color = "#888";
  }

  resDraft.textContent = result.gmail_draft_id ? "Created ✓" : "Not created";
  resDraft.style.color = result.gmail_draft_id ? "#4caf50" : "#666";

  // Update job card with parsed data
  jobCard.classList.remove("empty");
  jobTitle.textContent = result.job_title || jobTitle.textContent;
  jobCompany.textContent = result.company || jobCompany.textContent;

  resultBox.classList.add("visible");
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function setStatus(type, text) {
  statusBadge.className = `badge ${type}`;
  statusText.textContent = text;

  const dot = statusBadge.querySelector(".dot");
  if (dot) {
    dot.classList.toggle("pulse", type === "processing" || type === "scraping");
  }
}

function resetResult() {
  resultBox.classList.remove("visible");
  [resScore, resResume, resOutreach, resDraft].forEach((el) => {
    el.textContent = "—";
    el.className = "value";
    el.style.color = "";
  });
}
