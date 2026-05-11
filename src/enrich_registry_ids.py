#!/usr/bin/env python3
"""
Enrich CTI trials.json with registry IDs from ClinicalTrials.gov.

For each trial missing an NCT ID, searches by short name and full title.
Also handles trials with EudraCT numbers (YYYY-NNNNNN-NN format) by searching
CT.gov via EudraCT cross-reference and the EU Clinical Trials Register.

Validation uses three signals:
  1. Full title similarity (primary)
  2. Trial name appears verbatim in CT.gov title (boosts when title also agrees)
  3. CT.gov Condition field vs CTI cancer category (penalty for mismatches)

Usage:
    python3 src/enrich_registry_ids.py

Outputs:
    data/trials.json               — updated in place
    data/registry_search_report.txt — human-readable match report for review
"""

import json, re, time, requests
from difflib import SequenceMatcher

CTGOV_BASE   = "https://clinicaltrials.gov/api/v2/studies"
EUCTR_SEARCH = "https://www.clinicaltrialsregister.eu/ctr-search/search"
EUDRACT_RE   = re.compile(r"^\d{4}-\d{6}-\d{2}$")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Keywords expected in CT.gov Condition field for each CTI cancer category.
# At least one keyword must match; empty list = basket/unrestricted.
CATEGORY_CONDITIONS = {
    "Breast":                   ["breast"],
    "Skin Cancer":              ["melanoma", "skin", "derma"],
    "Lung":                     ["lung", "nsclc", "sclc", "pulmon", "thorac", "mesotheliom"],
    "Genitourinary":            ["kidney", "renal", "bladder", "prostate", "testicular",
                                 "urothelial", "genitourinary"],
    "Head & Neck":              ["head", "neck", "larynx", "pharynx", "oral", "thyroid",
                                 "oropharynx", "salivary"],
    # Paediatric oncology: CT.gov conditions usually name the cancer type (e.g. "Acute Leukemia")
    # rather than labelling it "paediatric" — use broad cancer terms as fallback
    "Paediatric":               ["pediatric", "paediatric", "childhood", "juvenile", "children",
                                 "infant", "leukemia", "leukaemia", "lymphoma", "neuroblastoma",
                                 "medulloblastoma", "ependymoma", "neoplasm", "cancer", "tumor",
                                 "tumour", "sarcoma", "glioma", "transplant"],
    "Central Nervous System":   ["brain", "gliom", "glioblastom", "gbm", "meningiom",
                                 "cns", "ependymom", "dipg", "pontine"],
    "Gastrointestinal":         ["colorectal", "colon", "rectal", "gastric", "esophag",
                                 "oesophag", "pancreatic", "liver", "hepat", "biliary",
                                 "cholangiocarcinoma", "gallbladder", "gastrointestinal"],
    "Gynaecological":           ["ovarian", "cervical", "uterine", "endometrial", "vulval",
                                 "vulvar", "gynecolog", "gynaecolog"],
    # Lymphoma & Blood Cancers: include specific MPN disease names — CT.gov lists
    # "Polycythemia Vera", "Essential Thrombocythemia", "Primary Myelofibrosis" individually
    # rather than the umbrella term "Myeloproliferative Neoplasms"
    "Lymphoma & Blood Cancers": ["lymphoma", "leukemia", "leukaemia", "cll", "cml", "aml",
                                 "myeloma", "myeloproliferative", "haematolog", "hematolog",
                                 "myelodysplastic", "transplant", "bone marrow", "blood cancer",
                                 "polycythemia", "thrombocythemia", "myelofibrosis",
                                 "hodgkin", "waldenstrom"],
    "Sarcoma":                  ["sarcoma"],
    "Basket (Multiple Types)":  [],
}


# ── ClinicalTrials.gov ────────────────────────────────────────────────────────

def sanitize_query(text, max_chars=80):
    """Strip non-ASCII and API-hostile characters; limit length."""
    import unicodedata
    # Normalise unicode (smart quotes → ASCII quotes, etc.)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    # Remove characters known to cause 400s (colons, slashes, backslashes, brackets)
    text = re.sub(r"[:/\\()\[\]{}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def ctgov_search(query, field="query.titles", page_size=8, retries=2):
    """Search CT.gov; return list of candidate dicts including Condition."""
    clean = sanitize_query(query)
    for attempt in range(retries + 1):
        try:
            r = requests.get(CTGOV_BASE, params={
                field: clean,
                "pageSize": page_size,
                "fields": "NCTId,BriefTitle,OfficialTitle,Condition",
            }, headers=HEADERS, timeout=15)
            r.raise_for_status()
            out = []
            for s in r.json().get("studies", []):
                proto = s.get("protocolSection", {})
                m     = proto.get("identificationModule", {})
                cond  = proto.get("conditionsModule", {}).get("conditions", [])
                out.append({
                    "nct_id":         m.get("nctId", ""),
                    "brief_title":    m.get("briefTitle", ""),
                    "official_title": m.get("officialTitle", ""),
                    "conditions":     cond,
                })
            return out
        except Exception as e:
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
            else:
                print(f"    [CT.gov error] {e}")
                return []
    return []


# ── EU Clinical Trials Register ───────────────────────────────────────────────

def euctr_search(query):
    """Search EUCTR HTML; extract EudraCT numbers and any cross-listed NCT IDs."""
    try:
        r = requests.get(EUCTR_SEARCH, params={"query": query}, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept-Encoding": "identity",
        }, timeout=15)
        r.raise_for_status()
        eudract_ids = re.findall(r"(\d{4}-\d{6}-\d{2})", r.text)
        nct_ids     = re.findall(r"(NCT\d{8})", r.text)
        return {
            "eudract_ids": list(dict.fromkeys(eudract_ids)),
            "nct_ids":     list(dict.fromkeys(nct_ids)),
        }
    except Exception as e:
        print(f"    [EUCTR error] {e}")
        return {"eudract_ids": [], "nct_ids": []}


# ── Matching logic ────────────────────────────────────────────────────────────

def similarity(a, b):
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


# Broad oncology terms — any condition containing one of these is a cancer study.
# Used to filter out completely non-oncological matches (Sickle Cell, Diabetes, etc.)
# before applying the category-specific check.
ONCOLOGY_TERMS = {
    "cancer", "carcinoma", "neoplasm", "tumor", "tumour", "sarcoma", "lymphoma",
    "leukemia", "leukaemia", "melanoma", "myeloma", "adenocarcinoma",
    "oncology", "malignant", "malignancy", "metastatic",
    # Haematological
    "polycythemia", "thrombocythemia", "myelofibrosis", "myeloproliferative",
    "myelodysplastic",
    # CNS / paediatric tumours — CT.gov often lists these by specific name
    "gliom", "glioblastom", "ependymom", "medulloblastom", "astrocytom",
    "meningiom", "neuroblastom", "retinoblastom", "nephroblastom",
    "craniopharyngiom", "germinoma",
    # Hepatobiliary
    "cholangiocarcinoma", "hepatocellular", "hepatoblastom",
    # Other
    "mesothelioma", "rhabdomyosarcom", "wilms",
}


def condition_compatible(category, conditions):
    """
    Return False if CT.gov conditions clearly contradict what we expect.

    Two-level check:
      1. Oncology gate: if no conditions contain any cancer-related term,
         this is a non-oncological study — cap score at 0.20.
      2. Category gate: if conditions don't match the specific CTI category,
         cap score at 0.20 (still allows LOW-confidence review for ambiguous cases).
    """
    if not conditions:
        return True

    conditions_text = " ".join(conditions).lower()

    # Gate 1: is this even oncology?
    if not any(term in conditions_text for term in ONCOLOGY_TERMS):
        return False

    # Gate 2: category-specific check
    if not category:
        return True
    keywords = CATEGORY_CONDITIONS.get(category, [])
    if not keywords:  # Basket or unknown — any oncology study is fine
        return True
    return any(kw in conditions_text for kw in keywords)


def score_candidate(name, full_title, category, candidate):
    """
    Return confidence score 0–1 for a CT.gov candidate.

    Signals used (in priority order):
      1. Full title similarity — primary disambiguation for generic acronyms.
      2. Name verbatim in CT.gov title — boosts well-known named trials where
         CT.gov plain-language brief title differs from the formal protocol title.
      3. Condition mismatch penalty — hard 0.20 cap when CT.gov conditions clearly
         don't match the CTI cancer category (e.g. Sickle Cell ≠ Lymphoma).
    """
    brief    = candidate["brief_title"]
    official = candidate["official_title"]
    conds    = candidate.get("conditions", [])

    name_found = (name.lower() in brief.lower()) or (name.lower() in official.lower())

    # Compute title-based score
    if full_title and len(full_title) > 30:
        title_sim = max(similarity(full_title, brief), similarity(full_title, official))
        if name_found and title_sim >= 0.45:
            score = 0.90
        else:
            score = title_sim
    else:
        if name_found:
            score = 0.75
        else:
            score = max(similarity(name, brief), similarity(name, official))

    # Condition mismatch penalty — prevents cross-indication false positives
    if not condition_compatible(category, conds):
        score = min(score, 0.20)

    return score


def best_ctgov_match(name, full_title, category, candidates):
    """Return (nct_id, score, matched_title) or None if nothing credible found."""
    scored = [
        (score_candidate(name, full_title, category, c), c)
        for c in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < 0.40:
        return None
    score, c = scored[0]
    title = c["brief_title"] or c["official_title"]
    return c["nct_id"], score, title


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open("data/trials.json") as f:
        trials = json.load(f)

    missing = [t for t in trials if not t.get("clinicaltrials_gov_id")]
    print(f"Searching registry IDs for {len(missing)} trials...\n")

    report_lines = [
        "CTI Registry Enrichment Report",
        "================================",
        f"Trials searched: {len(missing)}",
        "",
    ]

    auto_applied = 0
    needs_review = 0
    not_found    = 0

    for trial in missing:
        name       = trial["name"]
        full_title = (trial.get("full_title") or "").strip()
        number     = (trial.get("number") or "").strip()
        category   = trial.get("category", "")
        is_eudract = bool(EUDRACT_RE.match(number))

        print(f"[{name}]")
        report_lines.append(f"## {name}  ({number or 'no CTI number'})")

        candidates = []

        # Strategy 1: search by short trial name
        results = ctgov_search(name)
        candidates.extend(results)
        time.sleep(0.5)

        # Strategy 2: EudraCT cross-search
        if is_eudract:
            print(f"  → EudraCT number detected ({number}), cross-searching CT.gov...")
            results2 = ctgov_search(number, field="query.term")
            candidates.extend(results2)
            time.sleep(0.5)

        # Strategy 3: full title search when name search gave nothing strong.
        if full_title and len(full_title) > 30:
            best_so_far = best_ctgov_match(name, full_title, category, candidates)
            if not best_so_far or best_so_far[1] < 0.60:
                results3 = ctgov_search(full_title[:80])
                candidates.extend(results3)
                time.sleep(0.5)

        # Strategy 4: query.term (full-text search across ALL CT.gov fields including
        # secondary IDs and sponsor protocol numbers). Catches cooperative group trials
        # like "NRG GU012 SAMURAI" whose official title doesn't contain the acronym.
        # Sanitise the name first — em-dashes and slashes confuse the parser.
        best_so_far = best_ctgov_match(name, full_title, category, candidates)
        if not best_so_far or best_so_far[1] < 0.60:
            clean_name = re.sub(r"[–—/\\]", " ", name).strip()
            results4 = ctgov_search(clean_name, field="query.term")
            candidates.extend(results4)
            time.sleep(0.5)

        match = best_ctgov_match(name, full_title, category, candidates)

        if match:
            nct_id, score, matched_title = match
            if score >= 0.85:
                confidence = "HIGH"
            elif score >= 0.60:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            print(f"  {'✓' if confidence != 'LOW' else '?'} {nct_id}  [{confidence} {score:.2f}]")
            print(f"    → {matched_title[:90]}")

            trial["clinicaltrials_gov_id"]  = nct_id
            trial["clinicaltrials_gov_url"] = f"https://clinicaltrials.gov/study/{nct_id}"
            trial["nct_match_confidence"]   = confidence

            report_lines += [
                f"  NCT ID : {nct_id}",
                f"  Score  : {score:.2f} ({confidence})",
                f"  Match  : {matched_title}",
                f"  CT.gov : https://clinicaltrials.gov/study/{nct_id}",
            ]
            if confidence == "LOW":
                report_lines.append("  ⚠️  LOW confidence — verify manually")
                needs_review += 1
            else:
                auto_applied += 1

        else:
            print(f"  ✗  No match found")
            report_lines.append("  No match found on ClinicalTrials.gov")

            if is_eudract:
                print(f"  → Trying EUCTR for {number}...")
                euctr = euctr_search(name)
                if euctr["nct_ids"]:
                    nct_via_euctr = euctr["nct_ids"][0]
                    print(f"  ✓ Found via EUCTR cross-reference: {nct_via_euctr}")
                    trial["clinicaltrials_gov_id"]  = nct_via_euctr
                    trial["clinicaltrials_gov_url"] = f"https://clinicaltrials.gov/study/{nct_via_euctr}"
                    trial["nct_match_confidence"]   = "MEDIUM"
                    report_lines.append(f"  NCT via EUCTR cross-ref: {nct_via_euctr} (MEDIUM — verify)")
                    needs_review += 1
                elif euctr["eudract_ids"]:
                    found_id = euctr["eudract_ids"][0]
                    trial["euctr_id"]  = found_id
                    trial["euctr_url"] = (f"https://www.clinicaltrialsregister.eu"
                                          f"/ctr-search/search?query={found_id}")
                    print(f"  → EUCTR ID stored: {found_id}")
                    report_lines.append(f"  EudraCT found: {found_id} (no NCT cross-ref)")
                    not_found += 1
                else:
                    not_found += 1
            else:
                not_found += 1

        report_lines.append("")
        print()

    total_found = auto_applied + needs_review
    print(f"=== Results ===")
    print(f"  High/medium confidence (auto-applied): {auto_applied}")
    print(f"  Low confidence (needs review):         {needs_review}")
    print(f"  Not found:                             {not_found}")
    print(f"  Total new IDs added:                   {total_found} / {len(missing)}")

    report_lines += [
        "================================",
        f"High/medium confidence (auto-applied): {auto_applied}",
        f"Low confidence (needs manual review):  {needs_review}",
        f"Not found:                             {not_found}",
        f"Total new IDs added:                   {total_found} / {len(missing)}",
    ]

    with open("data/trials.json", "w") as f:
        json.dump(trials, f, indent=2)
    print("\ndata/trials.json updated.")

    with open("data/registry_search_report.txt", "w") as f:
        f.write("\n".join(report_lines) + "\n")
    print("data/registry_search_report.txt written.")


if __name__ == "__main__":
    main()
