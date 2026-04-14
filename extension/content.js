/**
 * content.js — AI Job Agent
 * ──────────────────────────
 * Injected into every page. Listens for a scrape request from popup.js,
 * extracts job posting content, and returns it.
 *
 * Smart extraction strategy:
 *   1. Try known job-site selectors (LinkedIn, Greenhouse, Lever, Workday, Indeed)
 *   2. Fall back to <article> or <main>
 *   3. Last resort: full body text (stripped of nav/footer noise)
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "scrape_job") {
    try {
      const result = extractJobContent();
      sendResponse({ success: true, data: result });
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
  }
  return true; // keep channel open for async sendResponse
});

function extractJobContent() {
  const url = window.location.href;
  const pageTitle = document.title;

  // ── Known selectors per job platform ──────────────────────────────────────
  const selectors = [
    // LinkedIn
    ".job-view-layout",
    ".jobs-description",
    ".jobs-unified-top-card",
    // Greenhouse
    "#app",
    ".job-post",
    // Lever
    ".posting",
    ".content",
    // Workday
    "[data-automation-id='jobPostingDescription']",
    // Indeed
    ".jobsearch-JobComponent",
    "#jobDescriptionText",
    // Ashby
    ".ashby-job-posting",
    // Generic
    "article",
    "[role='main']",
    "main",
  ];

  let container = null;
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim().length > 200) {
      container = el;
      break;
    }
  }

  let rawText;
  if (container) {
    rawText = cleanText(container.innerText);
  } else {
    // Fallback: strip nav, header, footer, sidebar from body
    rawText = extractFromBody();
  }

  return {
    url,
    page_title: pageTitle,
    raw_text: rawText.substring(0, 8000), // cap at 8k chars for API
  };
}

function cleanText(text) {
  return text
    .replace(/\t/g, " ")
    .replace(/ {3,}/g, "  ")
    .replace(/\n{4,}/g, "\n\n\n")
    .trim();
}

function extractFromBody() {
  // Clone body and remove noise elements
  const bodyClone = document.body.cloneNode(true);
  const noiseSelectors = [
    "nav", "header", "footer", "aside",
    ".navbar", ".sidebar", ".cookie", ".banner",
    "[aria-hidden='true']", "script", "style", "noscript",
  ];
  noiseSelectors.forEach((sel) => {
    bodyClone.querySelectorAll(sel).forEach((el) => el.remove());
  });
  return cleanText(bodyClone.innerText);
}
