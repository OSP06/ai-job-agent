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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
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

  const recruiter = extractRecruiter();

  return {
    url,
    page_title: pageTitle,
    raw_text: rawText.substring(0, 8000),
    linkedin_recruiter_name: recruiter.name,
    linkedin_recruiter_url:  recruiter.url,
  };
}

function extractRecruiter() {
  // Only attempt on LinkedIn job pages
  if (!window.location.hostname.includes("linkedin.com")) {
    return { name: null, url: null };
  }

  // Selectors for the recruiter / job poster on LinkedIn (multiple UI variants)
  const posterSelectors = [
    // 2024+ unified top card poster
    ".job-details-jobs-unified-top-card__job-poster-container a",
    // Hiring team card
    ".hirer-card__hirer-information a",
    ".jobs-poster__name",
    // Older layout
    ".jobs-details-top-card__job-poster a",
    ".hiring-team__contacts a",
  ];

  for (const sel of posterSelectors) {
    const el = document.querySelector(sel);
    if (!el) continue;

    // Get name from inner span or innerText
    const nameEl = el.querySelector("span:not(.visually-hidden)") || el;
    const name = nameEl.innerText?.trim();
    const url  = el.href?.split("?")[0]; // strip tracking params

    if (name && name.length > 2 && name.length < 80) {
      return { name, url: url || null };
    }
  }

  return { name: null, url: null };
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
