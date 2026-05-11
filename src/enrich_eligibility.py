#!/usr/bin/env python3
"""
Pull detailed inclusion/exclusion criteria from ClinicalTrials.gov API v2
for all 63 trials that have an NCT ID.

New fields added to each trial:
  inclusion_criteria  — list of criterion strings
  exclusion_criteria  — list of criterion strings
  eligibility_min_age — e.g. "18 Years"
  eligibility_max_age — e.g. "N/A" or "75 Years"
  eligibility_sex     — "ALL", "FEMALE", or "MALE"
  eligibility_std_ages — list, e.g. ["ADULT", "OLDER_ADULT"]
  eligibility_raw     — full unmodified text from CT.gov

Usage:
    python3 src/enrich_eligibility.py
"""

import json, re, time, sqlite3, csv, requests
from pathlib import Path

BASE_URL = "https://clinicaltrials.gov/api/v2/studies/{}"
HEADERS = {"Accept": "application/json"}


def fetch_eligibility(nct_id, retries=3):
    url = BASE_URL.format(nct_id)
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                return data.get("protocolSection", {}).get("eligibilityModule", {})
            if r.status_code == 404:
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"    ERROR fetching {nct_id}: {e}")
    return None


def extract_items(block):
    """Parse a criteria block into a list of individual criterion strings.

    Handles three CT.gov formats:
      - Markdown bullets:  * criterion text
      - Numbered lists:    1. criterion text
      - Plain paragraphs:  separated by blank lines
    Sub-bullets and continuation lines are folded into the parent item.
    """
    if not block.strip():
        return []

    block = block.strip()
    # Unescape markdown backslash sequences CT.gov sometimes emits
    block = re.sub(r"\\([<>()\[\]#])", r"\1", block)

    items = []
    current = None

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        is_bullet   = bool(re.match(r"^\*\s+", stripped))
        is_numbered = bool(re.match(r"^\d+[.)]\s+", stripped))
        is_sub      = bool(re.match(r"^[+\-]\s+", stripped))

        if is_bullet:
            if current is not None:
                items.append(current)
            current = re.sub(r"^\*\s+", "", stripped)
        elif is_numbered:
            if current is not None:
                items.append(current)
            current = re.sub(r"^\d+[.)]\s+", "", stripped)
        elif is_sub:
            if current is not None:
                current += " " + stripped
        elif current is not None:
            current += " " + stripped          # continuation
        elif not stripped.endswith(":"):
            current = stripped                 # first line, no header

    if current and current.strip():
        items.append(current.strip())

    return [re.sub(r"\s+", " ", i).strip() for i in items if i.strip()]


def parse_criteria(text):
    """Split raw eligibility text into inclusion and exclusion lists.

    Handles CT.gov header variants (colon optional, any prefix/suffix):
      'Inclusion Criteria:'            'Key Inclusion Criteria:'
      'Inclusion Criteria for enrolment:'   'Inclusion criteria Phase 1'
      'Core Treatment - Inclusion Criteria:' (and equivalent Exclusion variants)

    Supports multi-phase trials (e.g. ITCC 054) where each phase has its own
    inclusion and exclusion sections — all inclusion sections are combined and
    deduplicated, likewise for exclusion.
    """
    if not text:
        return [], []

    text = text.replace("•", "*").replace("–", "-")
    text = re.sub(r"\\([<>()\[\]#])", r"\1", text)

    # Find all header lines that contain "inclusion criteria" or "exclusion criteria"
    header_re = re.compile(
        r"^[^\n]*?(?P<kind>inclusion|exclusion)\s+criteria[^\n]*?:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    headers = [
        (m.start(), m.end(), "incl" if m.group("kind").lower() == "inclusion" else "excl")
        for m in header_re.finditer(text)
    ]

    if not headers:
        return extract_items(text), []

    incl_segments, excl_segments = [], []
    for i, (start, end, kind) in enumerate(headers):
        content_start = end + 1
        content_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        segment = text[content_start:content_end].strip()
        if kind == "incl":
            incl_segments.append(segment)
        else:
            excl_segments.append(segment)

    def combine(segments):
        seen, items = set(), []
        for seg in segments:
            for item in extract_items(seg):
                if item not in seen:
                    seen.add(item)
                    items.append(item)
        return items

    return combine(incl_segments), combine(excl_segments)


def enrich_trials():
    with open("data/trials.json") as f:
        trials = json.load(f)

    nct_trials = [t for t in trials if t.get("clinicaltrials_gov_id")]
    print(f"Fetching eligibility for {len(nct_trials)} NCT trials...\n")

    hits = 0
    for i, trial in enumerate(nct_trials):
        nct_id = trial["clinicaltrials_gov_id"]
        print(f"  [{i+1:02d}/{len(nct_trials)}] {trial['name']} ({nct_id})")

        em = fetch_eligibility(nct_id)
        if not em:
            print(f"    — no data returned")
            time.sleep(0.3)
            continue

        raw_text = em.get("eligibilityCriteria", "")
        incl, excl = parse_criteria(raw_text)

        trial["inclusion_criteria"] = incl
        trial["exclusion_criteria"] = excl
        trial["eligibility_min_age"] = em.get("minimumAge")
        trial["eligibility_max_age"] = em.get("maximumAge")
        trial["eligibility_sex"] = em.get("sex")
        trial["eligibility_std_ages"] = em.get("stdAges", [])
        trial["eligibility_raw"] = raw_text

        print(f"    ✓ {len(incl)} inclusion, {len(excl)} exclusion criteria")
        hits += 1
        time.sleep(0.35)

    # Ensure non-NCT trials have empty fields
    for trial in trials:
        if not trial.get("clinicaltrials_gov_id"):
            for field in ["inclusion_criteria", "exclusion_criteria",
                          "eligibility_min_age", "eligibility_max_age",
                          "eligibility_sex", "eligibility_std_ages", "eligibility_raw"]:
                trial.setdefault(field, None)

    save_json(trials)
    save_csv(trials)
    save_db(trials)
    print(f"\nEnriched {hits}/{len(nct_trials)} NCT trials.")


def save_json(trials):
    with open("data/trials.json", "w") as f:
        json.dump(trials, f, indent=2, ensure_ascii=False)
    print("data/trials.json updated.")


def save_csv(trials):
    fieldnames = [
        "name", "number", "category", "phase", "type", "sponsor",
        "principal_investigator", "patient_population", "purpose", "sites",
        "recruitment_started_ireland", "global_target", "ireland_target",
        "clinicaltrials_gov_id", "clinicaltrials_gov_url",
        "registry", "registry_id", "registry_url", "registry_confidence",
        "protocol_public", "protocol_note", "trial_status",
        "eligibility_min_age", "eligibility_max_age", "eligibility_sex",
        "url",
    ]
    with open("data/trials.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        rows = []
        for t in trials:
            row = dict(t)
            # Flatten list fields to semicolon-separated
            for field in ["eligibility_std_ages"]:
                if isinstance(row.get(field), list):
                    row[field] = "; ".join(row[field])
            rows.append(row)
        writer.writerows(rows)
    print("data/trials.csv updated.")


def save_db(trials):
    conn = sqlite3.connect("data/trials.db")
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS trials")
    c.execute("""
        CREATE TABLE trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, number TEXT, category TEXT, url TEXT,
            full_title TEXT, phase TEXT, type TEXT, sponsor TEXT,
            principal_investigator TEXT, patient_population TEXT,
            purpose TEXT, about TEXT, sites TEXT,
            recruitment_started_global TEXT, recruitment_started_ireland TEXT,
            global_target TEXT, ireland_target TEXT,
            clinicaltrials_gov_id TEXT, clinicaltrials_gov_url TEXT,
            registry TEXT, registry_id TEXT, registry_url TEXT,
            registry_confidence TEXT, protocol_public INTEGER,
            protocol_note TEXT, trial_status TEXT,
            inclusion_criteria TEXT, exclusion_criteria TEXT,
            eligibility_min_age TEXT, eligibility_max_age TEXT,
            eligibility_sex TEXT, eligibility_std_ages TEXT,
            eligibility_raw TEXT,
            scraped_date TEXT
        )
    """)
    for t in trials:
        c.execute("""
            INSERT INTO trials VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t.get("name"), t.get("number"), t.get("category"), t.get("url"),
            t.get("full_title"), t.get("phase"), t.get("type"), t.get("sponsor"),
            t.get("principal_investigator"), t.get("patient_population"),
            t.get("purpose"), t.get("about"), t.get("sites"),
            t.get("recruitment_started_global"), t.get("recruitment_started_ireland"),
            t.get("global_target"), t.get("ireland_target"),
            t.get("clinicaltrials_gov_id"), t.get("clinicaltrials_gov_url"),
            t.get("registry"), t.get("registry_id"), t.get("registry_url"),
            t.get("registry_confidence"), 1 if t.get("protocol_public") else 0,
            t.get("protocol_note"), t.get("trial_status"),
            json.dumps(t.get("inclusion_criteria") or []),
            json.dumps(t.get("exclusion_criteria") or []),
            t.get("eligibility_min_age"), t.get("eligibility_max_age"),
            t.get("eligibility_sex"),
            json.dumps(t.get("eligibility_std_ages") or []),
            t.get("eligibility_raw"),
            "2026-05-09",
        ))
    conn.commit()
    conn.close()
    print("data/trials.db updated.")


if __name__ == "__main__":
    print("=== CTI Eligibility Enrichment ===\n")
    enrich_trials()
    print("\nDone.")
