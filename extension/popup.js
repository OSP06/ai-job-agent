/**
 * popup.js — AI Job Agent
 */

const DEFAULT_BACKEND = "https://ai-job-agent-8zrr.onrender.com";

// ─── State ────────────────────────────────────────────────────────────────────
let scrapedData      = null;
let backendUrl       = DEFAULT_BACKEND;
let notionUrl        = "";
let outreachExpanded = false;

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const jobCard           = document.getElementById("jobCard");
const jobTitle          = document.getElementById("jobTitle");
const jobCompany        = document.getElementById("jobCompany");
const jobUrl            = document.getElementById("jobUrl");
const statusBadge       = document.getElementById("statusBadge");
const statusText        = document.getElementById("statusText");
const processBtn        = document.getElementById("processBtn");
const refreshBtn        = document.getElementById("refreshBtn");
const resultBox         = document.getElementById("resultBox");
const resScore          = document.getElementById("resScore");
const resResume         = document.getElementById("resResume");
const resOutreach       = document.getElementById("resOutreach");
const resAppLink        = document.getElementById("resAppLink");
const outreachPanel     = document.getElementById("outreachPanel");
const emailSubject      = document.getElementById("emailSubject");
const emailBody         = document.getElementById("emailBody");
const copyBtn           = document.getElementById("copyBtn");
const applyBar          = document.getElementById("applyBar");
const applyBtn          = document.getElementById("applyBtn");
const scoresDivider     = document.getElementById("scoresDivider");
const scoresSection     = document.getElementById("scoresSection");
const scoresBars        = document.getElementById("scoresBars");
const contactDivider    = document.getElementById("contactDivider");
const contactsSection   = document.getElementById("contactsSection");
const contactsContainer = document.getElementById("contactsContainer");
const backendUrlInput   = document.getElementById("backendUrlInput");
const saveUrlBtn        = document.getElementById("saveUrlBtn");
const notionUrlInput    = document.getElementById("notionUrlInput");
const saveNotionBtn     = document.getElementById("saveNotionBtn");
const skillsDivider     = document.getElementById("skillsDivider");
const skillsSection     = document.getElementById("skillsSection");
const matchedSection    = document.getElementById("matchedSection");
const missingSection    = document.getElementById("missingSection");
const matchedPills      = document.getElementById("matchedPills");
const missingPills      = document.getElementById("missingPills");
const scoreHero         = document.getElementById("scoreHero");
const scoreRingEl       = document.getElementById("scoreRing");

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Restore last result if the popup was closed by opening a tab (e.g. LinkedIn click)
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    chrome.storage.local.get(["backendUrl", "notionUrl", "lastResult"], (stored) => {
      backendUrl = stored.backendUrl || DEFAULT_BACKEND;
      backendUrlInput.value = backendUrl;
      notionUrl = stored.notionUrl || "";
      notionUrlInput.value = notionUrl;

      if (stored.lastResult && stored.lastResult.url === tab.url) {
        // Restore without re-scanning
        scrapedData = { url: tab.url, raw_text: "" };
        displayPreview({ url: tab.url }, tab);
        displayResult(stored.lastResult.result);
        setStatus("success", "Done ✓");
        processBtn.disabled = false;
      } else {
        scrapeCurrentTab();
      }
    });
  });

  processBtn.addEventListener("click", handleProcess);

  refreshBtn.addEventListener("click", () => {
    chrome.storage.local.remove("lastResult");
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

  saveNotionBtn.addEventListener("click", () => {
    const val = notionUrlInput.value.trim();
    notionUrl = val;
    chrome.storage.local.set({ notionUrl: val }, () => {
      saveNotionBtn.textContent = "Saved ✓";
      setTimeout(() => { saveNotionBtn.textContent = "Save"; }, 1500);
    });
  });

  document.getElementById("appsLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: notionUrl || `${backendUrl}/dashboard` });
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
  jobTitle.textContent   = parts[0]?.trim() || "Job Posting";
  jobCompany.textContent = parts[1]?.trim() || "";
  try { jobUrl.textContent = new URL(data.url).hostname; } catch { jobUrl.textContent = data.url; }
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

    if (resp.status === 409) {
      const err = await resp.json().catch(() => ({}));
      const id = (err.detail || "").split(":")[1];
      setStatus("idle", `Already captured${id ? ` — Application #${id}` : ""}`);
      processBtn.disabled = false;
      refreshBtn.disabled = false;
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    displayResult(result);
    setStatus("success", "Done ✓");
    // Persist so popup can restore if closed by a tab-open (e.g. LinkedIn click)
    chrome.storage.local.set({ lastResult: { url: scrapedData.url, result } });

  } catch (err) {
    setStatus("error", `Error: ${err.message}`);
  } finally {
    processBtn.disabled = false;
    refreshBtn.disabled = false;
  }
}

// ─── Display result ───────────────────────────────────────────────────────────
function displayResult(result) {
  const score     = result.match_score;
  const scorePct  = pct(score);
  const threshold = parseThreshold(result.outreach_skipped_reason) ?? 0.5;

  // ── Score hero ──
  resScore.textContent = scorePct;
  resScore.className   = "score-number " + scoreClass(score, threshold);
  scoreHero.className  = "score-hero "   + scoreClass(score, threshold);
  // Animate ring: reset to empty, then animate to score value
  const _circ = 2 * Math.PI * 32;
  scoreRingEl.style.strokeDashoffset = String(_circ);
  setTimeout(() => { scoreRingEl.style.strokeDashoffset = String(_circ * (1 - score)); }, 80);
  resResume.textContent = result.resume_used || "—";

  // Update job card accent colour
  jobCard.className = "job-card " + scoreClass(score, threshold);
  jobCard.classList.remove("empty");
  if (result.job_title) jobTitle.textContent   = result.job_title;
  if (result.company)   jobCompany.textContent = result.company;

  // ── Outreach ──
  if (result.outreach_generated) {
    const hasContent = result.outreach_subject || result.outreach_body;
    if (hasContent) {
      resOutreach.textContent = "View email ↓";
      resOutreach.className   = "value clickable";
      emailSubject.textContent = result.outreach_subject || "";
      emailBody.textContent    = result.outreach_body    || "";
      resOutreach.onclick = () => {
        outreachExpanded = !outreachExpanded;
        outreachPanel.style.display = outreachExpanded ? "block" : "none";
        resOutreach.textContent = outreachExpanded ? "Hide email ↑" : "View email ↓";
      };
    } else {
      resOutreach.textContent = "Generated ✓";
      resOutreach.className   = "value success";
    }
  } else {
    resOutreach.textContent = result.outreach_skipped_reason || `Skipped (${scorePct})`;
    resOutreach.className   = "value muted";
  }

  // ── Application link ──
  if (result.application_id) {
    resAppLink.textContent = `#${result.application_id} — view →`;
    resAppLink.onclick = () => chrome.tabs.create({
      url: `${backendUrl}/api/applications/${result.application_id}`,
    });
  }

  // ── Copy button ──
  copyBtn.onclick = () => {
    const text = `Subject: ${emailSubject.textContent}\n\n${emailBody.textContent}`;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.textContent = "Copied ✓";
      setTimeout(() => { copyBtn.textContent = "Copy email"; }, 2000);
    });
  };

  // ── Apply bar ──
  if (result.application_id && result.status === "captured") {
    applyBar.style.display = "";
    applyBtn.disabled      = false;
    applyBtn.textContent   = "Mark as Applied";
    applyBtn.style.color   = "";
    applyBtn.onclick = async () => {
      applyBtn.disabled    = true;
      applyBtn.textContent = "Marking…";
      try {
        await fetch(`${backendUrl}/api/applications/${result.application_id}/apply`, { method: "POST" });
        applyBtn.textContent = "Applied ✓";
        applyBtn.style.color = "#22c55e";
        result.status = "applied";
        chrome.storage.local.get("lastResult", (s) => {
          if (s.lastResult) {
            s.lastResult.result.status = "applied";
            chrome.storage.local.set({ lastResult: s.lastResult });
          }
        });
      } catch {
        applyBtn.disabled    = false;
        applyBtn.textContent = "Mark as Applied";
      }
    };
  }

  // ── Contacts ──
  const contacts = result.contacts_found || [];
  contactDivider.style.display  = "";
  contactsSection.style.display = "";
  contactsContainer.innerHTML   = "";

  if (contacts.length) {
    contacts.slice(0, 3).forEach((c, idx) => {
      const initials = getInitials(c.name);
      const hasLink  = !!c.linkedin_url;
      const nameHtml = escHtml(c.name || "Unknown")
        + (c.verified ? ' <span class="check">✓</span>' : "");

      const card = document.createElement("div");
      card.className = `contact-card${hasLink ? " has-link" : ""}`;
      card.innerHTML = `
        <div class="contact-avatar avatar-${idx % 5}${c.verified ? " verified" : ""}">${escHtml(initials)}</div>
        <div class="contact-details">
          <div class="contact-name">${nameHtml}</div>
          ${c.title ? `<div class="contact-role">${escHtml(c.title)}</div>` : ""}
        </div>
        ${hasLink ? '<div class="contact-arrow">↗</div>' : ""}`;

      if (hasLink) card.onclick = () => chrome.tabs.create({ url: c.linkedin_url });
      contactsContainer.appendChild(card);
    });
  } else {
    contactsContainer.innerHTML =
      `<div class="no-contacts">No contacts found for this company</div>`;
  }

  // ── Skills ──
  const matched = result.matched_skills || [];
  const missing = result.missing_skills || [];
  if (matched.length || missing.length) {
    skillsDivider.style.display = "";
    skillsSection.style.display = "";
    if (matched.length) {
      matchedSection.style.display = "";
      matchedPills.innerHTML = matched.slice(0, 8)
        .map(s => `<span class="pill match">${escHtml(s)}</span>`).join("");
    }
    if (missing.length) {
      missingSection.style.display = "";
      missingPills.innerHTML = missing.slice(0, 6)
        .map(s => `<span class="pill missing">${escHtml(s)}</span>`).join("");
    }
  }

  // ── Resume score bars ──
  const allScores = result.all_resume_scores || {};
  const names = Object.keys(allScores);
  if (names.length > 1) {
    scoresDivider.style.display = "";
    scoresSection.style.display = "";
    scoresBars.innerHTML = "";

    const maxScore = Math.max(...Object.values(allScores), 0.01);
    names.sort((a, b) => allScores[b] - allScores[a]);

    names.forEach((name) => {
      const s      = allScores[name];
      const isBest = name === result.resume_used;
      const barPct = Math.round((s / maxScore) * 100);
      const fillCls = isBest
        ? (s >= threshold ? "bar-fill best" : "bar-fill low")
        : "bar-fill";

      scoresBars.innerHTML += `
        <div class="score-bar-row">
          <span class="sname${isBest ? " best" : ""}">${escHtml(name)}</span>
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

function getInitials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.substring(0, 2).toUpperCase();
}

function escHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function setStatus(type, text) {
  statusBadge.className = `badge ${type}`;
  statusText.textContent = text;
  const dot = statusBadge.querySelector(".dot");
  if (dot) dot.classList.toggle("pulse", type === "processing" || type === "scraping");
}

function resetResult() {
  resultBox.classList.remove("visible");
  outreachExpanded = false;
  outreachPanel.style.display = "none";

  resScore.textContent  = "—";
  resScore.className    = "score-number";
  scoreHero.className   = "score-hero";
  scoreRingEl.style.strokeDashoffset = String(2 * Math.PI * 32);
  resResume.textContent = "—";

  resOutreach.textContent = "—";
  resOutreach.className   = "value";
  resOutreach.onclick     = null;

  resAppLink.textContent = "—";
  resAppLink.onclick     = null;

  applyBar.style.display = "none";

  contactDivider.style.display  = "none";
  contactsSection.style.display = "none";
  contactsContainer.innerHTML   = "";

  skillsDivider.style.display = "none";
  skillsSection.style.display = "none";
  matchedSection.style.display = "none";
  missingSection.style.display = "none";
  matchedPills.innerHTML = "";
  missingPills.innerHTML = "";

  scoresDivider.style.display = "none";
  scoresSection.style.display = "none";
  scoresBars.innerHTML = "";

  jobCard.className = "job-card";
}
