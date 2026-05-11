# CTI Trial Database

A scraped, structured database of all active clinical trials listed on [Cancer Trials Ireland](https://cancertrials.ie), with an interactive browser-based viewer.

**Last scraped:** May 2026  
**Trials captured:** 82 across 11 cancer type categories

## Quick Start

Open `src/index.html` in any browser — no server required.

## Re-scrape

```bash
pip install requests beautifulsoup4
python3 src/scrape.py
```

## Data

- `data/trials.json` — full enriched data (source of truth)
- `data/trials.csv` — flat CSV
- `data/trials.db` — SQLite database

## See CLAUDE.md

Full project context, schema documentation, known gaps, and suggested next steps are in `CLAUDE.md`.
