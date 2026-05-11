# CLAUDE.md — CTI Trial Database

This file gives you everything you need to pick up this project seamlessly.

---

## Who You're Working With

**Rob Brown** — co-founder of [Evident](https://evident.med / evident.vet), a healthcare and veterinary AI startup that builds graph RAG pipelines to extract structured knowledge from unstructured medical records. Rob is also a facilitator at Attuned.ie who runs AI workshops for business audiences.

**Evident's current commercial focus** is a multi-site pilot with **Cancer Trials Ireland (CTI)**, targeting oncology sites including the Mater, Beacon, St. Luke's Dublin, University of Limerick, and University of Galway. The core Evident stack uses on-premises GPU deployment (7–13B parameter models, vLLM inference), Neo4j for graph storage, and LangChain for RAG pipelines. Data residency and on-premises deployment are non-negotiable requirements for hospital partners.

**Why this database matters:** Rob needs a comprehensive, queryable picture of every trial CTI is currently running — which sites are involved, which sponsors, what the patient populations look like — to inform Evident's pilot strategy and understand where clinical trial documentation (the kind Evident processes) is being generated across the CTI network.

---

## What This Project Is

A scraped, structured database of all **82 active clinical trials** listed on [Cancer Trials Ireland](https://cancertrials.ie), built in May 2026.

CTI is Ireland's primary academic clinical trials organisation, running trials across 19 hospital sites nationally. Their website lists trials by cancer type category; the trial search page itself is a JS-rendered widget that can't be statically scraped, but the category pages and individual trial pages are static HTML.

---

## Project Structure

```
cti-trials-db/
├── CLAUDE.md           ← you are here
├── README.md           ← user-facing docs
├── requirements.txt    ← Python dependencies
├── src/
│   ├── scrape.py       ← scraper (run from project root)
│   └── index.html      ← standalone interactive database viewer
└── data/
    ├── trials.json     ← full enriched data (source of truth)
    ├── trials.csv      ← flat CSV export
    └── trials.db       ← SQLite database
```

---

## Data Schema

Each trial record in `trials.json` / `trials.db` has these fields:

| Field | Description |
|---|---|
| `name` | Short trial name (e.g. "Mountaineer-03") |
| `number` | CTRIAL-IE number (e.g. "23-25") |
| `category` | Cancer type category from CTI site |
| `url` | CTI detail page URL |
| `full_title` | Full formal trial title |
| `type` | "Industry Sponsored", "Collaborative", or "In-House" |
| `sponsor` | Sponsoring company or institution |
| `principal_investigator` | Named Irish PI(s) and their sites |
| `patient_population` | Eligibility summary |
| `purpose` | Plain-language trial purpose |
| `about` | Longer description from detail page |
| `sites` | Irish hospital sites running this trial |
| `recruitment_started_global` | Global recruitment start date |
| `recruitment_started_ireland` | Ireland recruitment start date |
| `global_target` | Global patient recruitment target |
| `ireland_target` | Ireland-specific target |
| `clinicaltrials_gov_id` | NCT number (present for ~60% of trials) |
| `clinicaltrials_gov_url` | Direct link to ClinicalTrials.gov entry |

**Coverage stats at time of scrape:**
- 82 total active trials
- 11 cancer type categories
- 50/82 with ClinicalTrials.gov NCT IDs
- Trial types: 32 Industry Sponsored, 33 Collaborative, 7 In-House, ~9 unknown

**Known gaps:**
- `phase` field: CTI doesn't publish trial phase on their site; would need to pull from ClinicalTrials.gov
- Some trials (especially paediatric registries and observational studies) have minimal metadata
- Sites field is free text from the detail page — not yet normalised to a site lookup table
- The scraper was run once; there's no incremental update / change-detection logic yet

---

## The Interactive Viewer (`src/index.html`)

A fully self-contained single-file HTML app. Open directly in a browser — no server needed. Features:
- Full-text search across name, sponsor, PI, purpose, patient population, sites
- Filter by cancer category, trial type, NCT ID presence
- Card grid view with click-to-expand modal
- Direct links to CTI trial pages and ClinicalTrials.gov

The trial data is embedded inline in the HTML as a JS constant. When you re-scrape, you'll need to regenerate the HTML or update the embedded JSON.

---

## Re-running the Scraper

```bash
pip install requests beautifulsoup4
python3 src/scrape.py
```

Run from the project root. Outputs overwrite `data/trials.json`, `data/trials.csv`, `data/trials.db`.

The scraper uses polite delays (0.3–0.4s between requests). CTI's site is on WP Engine with Cloudflare — requires a realistic browser User-Agent string and `Accept-Encoding: identity` (no compression) to avoid being blocked.

---

## Suggested Next Steps

These are directions Rob has indicated interest in, roughly prioritised:

1. **Pull ClinicalTrials.gov data for all 50 NCT trials** — phase, study design, endpoints, arms, full eligibility criteria, document links. The ClinicalTrials.gov API (`https://clinicaltrials.gov/api/v2/studies/{NCT_ID}`) is free and well-documented.

2. **Normalise the `sites` field** — parse the free-text sites string into a structured lookup table of Irish hospital sites (Mater, Beaumont, St. Vincent's, etc.) so you can query "which trials run at the Mater?" — directly relevant to Evident's pilot sites.

3. **Add protocol document sourcing** — CTI doesn't publish protocols publicly, but ClinicalTrials.gov often has document sections. EUCTR (EU Clinical Trials Register) is another source. Some trials link to publications or lay summaries.

4. **Build a site-centric view** — a dashboard showing, for each hospital site, which trials they're running, in which categories, with which sponsors. Useful for Evident's site-by-site pilot targeting.

5. **Add incremental scraping / change detection** — track when trials are added, removed, or updated (recruitment status, site additions). Could store a snapshot per run in the SQLite DB.

6. **Upgrade the viewer to a proper web app** — the current `index.html` is a static file. Could become a Flask/FastAPI backend querying the SQLite DB, with more advanced filtering, export, and eventually Evident-specific features (e.g. tagging trials by Evident deployment status).

---

## Context on CTI's Structure

- CTI operates through **Disease-Specific Study Groups (DSSGs)** — one per cancer type — which govern which trials open in Ireland
- Trials are categorised as: **Industry Sponsored** (pharma-funded), **Collaborative** (academic/cooperative group), or **In-House** (CTI-originated)
- CTI has a network of **19 hospital sites** across Ireland and Northern Ireland
- Each trial has a named Irish **Principal Investigator (PI)** — often multiple PIs across sites
- CTRIAL-IE numbers (e.g. "23-25") are CTI's internal reference system; the year prefix indicates when the trial was registered with CTI
