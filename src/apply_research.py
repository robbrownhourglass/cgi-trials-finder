#!/usr/bin/env python3
"""
Apply manual registry-sleuthing research results to trials.json, trials.csv, and trials.db.
Adds fields: registry, registry_id, registry_url, protocol_public,
             protocol_note, registry_confidence, trial_status.
Run from project root:
    python3 src/apply_research.py
"""

import json, sqlite3, csv
from datetime import date

# ── Research results ─────────────────────────────────────────────────────────
#
# Each entry is keyed by exact trial name from trials.json.
# Keys used:
#   clinicaltrials_gov_id / clinicaltrials_gov_url  — CT.gov NCT
#   registry / registry_id / registry_url            — canonical registry
#   registry_confidence                              — HIGH / MEDIUM / LOW / N/A
#   protocol_public                                  — True/False
#   protocol_note
#   trial_status                                     — "Active" (default) / "TERMINATED"
#   _clear_nct                                       — True = remove wrong NCT match

RESEARCH = {

    # ── ClinicalTrials.gov confirmed ─────────────────────────────────────────

    "PRISM": {
        "clinicaltrials_gov_id":  "NCT07425002",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT07425002",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT07425002",
        "registry_url":           "https://clinicaltrials.gov/study/NCT07425002",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Cancer Trials Ireland sponsor. CTRIAL-IE 25-15.",
    },
    "DESTINY-Breast15": {
        "clinicaltrials_gov_id":  "NCT05950945",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT05950945",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT05950945",
        "registry_url":           "https://clinicaltrials.gov/study/NCT05950945",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Daiichi Sankyo, T-DXd HER2-low breast cancer Phase 3b.",
    },
    "PRIMROSE CSF": {
        "clinicaltrials_gov_id":  "NCT07503704",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT07503704",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT07503704",
        "registry_url":           "https://clinicaltrials.gov/study/NCT07503704",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "RCSI sponsor. CSF cell-free DNA in breast cancer CNS disease.",
    },
    "ALIDHE": {
        "clinicaltrials_gov_id":  "NCT05907057",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT05907057",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT05907057",
        "registry_url":           "https://clinicaltrials.gov/study/NCT05907057",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Servier, ivosidenib + azacitidine, IDH1-mutant AML Phase 3b.",
    },
    "ANTHOS ANT 008 – Magnolia": {
        "clinicaltrials_gov_id":  "NCT05171075",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT05171075",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT05171075",
        "registry_url":           "https://clinicaltrials.gov/study/NCT05171075",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Anthos Therapeutics, abelacimab vs dalteparin, cancer-associated VTE.",
        "trial_status":           "TERMINATED",
    },
    "TPAC": {
        "clinicaltrials_gov_id":  "NCT06287294",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT06287294",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT06287294",
        "registry_url":           "https://clinicaltrials.gov/study/NCT06287294",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Our Lady's Hospice, taste/xerostomia in advanced cancer.",
    },
    "MOSAICC": {
        "clinicaltrials_gov_id":  "NCT01831635",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT01831635",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT01831635",
        "registry_url":           "https://clinicaltrials.gov/study/NCT01831635",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "MPN case-control study. Queen's University Belfast sponsor.",
    },
    "LCH IV": {
        "clinicaltrials_gov_id":  "NCT02205762",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT02205762",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT02205762",
        "registry_url":           "https://clinicaltrials.gov/study/NCT02205762",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Langerhans Cell Histiocytosis. North American Consortium for Histiocytosis (NACHO) sponsor.",
    },
    "SIOP EPENDYMOMA II": {
        "clinicaltrials_gov_id":  "NCT02265770",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT02265770",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT02265770",
        "registry_url":           "https://clinicaltrials.gov/study/NCT02265770",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "Centre Léon Bérard, paediatric ependymoma programme.",
    },
    "ITCC 054": {
        "clinicaltrials_gov_id":  "NCT04258943",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT04258943",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT04258943",
        "registry_url":           "https://clinicaltrials.gov/study/NCT04258943",
        "registry_confidence":    "MEDIUM",
        "protocol_public":        True,
        "protocol_note":          "Bosutinib paediatric CML. Children's Oncology Group lead; ITCC-054 is the ITCC consortium designation for the same study.",
    },
    "Interfant 06": {
        "clinicaltrials_gov_id":  "NCT00550992",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT00550992",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT00550992",
        "registry_url":           "https://clinicaltrials.gov/study/NCT00550992",
        "registry_confidence":    "MEDIUM",
        "protocol_public":        True,
        "protocol_note":          "Dutch Childhood Oncology Group, infant ALL protocol. Status UNKNOWN on CT.gov — old trial, may be complete.",
    },
    "NRG GU012 SAMURAI": {
        "clinicaltrials_gov_id":  "NCT05327686",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT05327686",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT05327686",
        "registry_url":           "https://clinicaltrials.gov/study/NCT05327686",
        "registry_confidence":    "HIGH",
        "protocol_public":        True,
        "protocol_note":          "NRG Oncology, SABR ± immunotherapy for metastatic unresected renal cell carcinoma.",
    },
    "IMPROVE TMZ": {
        "clinicaltrials_gov_id":  "NCT06546631",
        "clinicaltrials_gov_url": "https://clinicaltrials.gov/study/NCT06546631",
        "registry":               "ClinicalTrials.gov",
        "registry_id":            "NCT06546631",
        "registry_url":           "https://clinicaltrials.gov/study/NCT06546631",
        "registry_confidence":    "HIGH",
        "protocol_public":        False,
        "protocol_note":          "UCC pharmacokinetic/observational study. PI: Prof Jack Gleeson. Registered on CT.gov; full protocol document not publicly available.",
    },

    # ── Other registries ─────────────────────────────────────────────────────

    "TOURIST Platform Trial – Thoracic Umbrella Radiotherapy Study in stage IV NSCLC": {
        "registry":            "ISRCTN",
        "registry_id":         "ISRCTN52137148",
        "registry_url":        "https://www.isrctn.com/ISRCTN52137148",
        "registry_confidence": "HIGH",
        "protocol_public":     True,
        "protocol_note":       "Full protocol registered with UK HRA and ISRCTN. NIHR-funded. Sponsor: The Christie NHS Foundation Trust. Contains PRINCE and QUARTZ LUNG sub-studies.",
    },
    "CARDIA Trial": {
        "_clear_nct":          True,  # NCT00938470 was a wrong match
        "registry":            "DRKS",
        "registry_id":         "DRKS00016923",
        "registry_url":        "https://drks.de/search/en/trial/DRKS00016923",
        "registry_confidence": "HIGH",
        "protocol_public":     True,
        "protocol_note":       "Protocol published open-access in BMC Cancer (DOI: 10.1186/s12885-020-07152-1). Registered on German DRKS. Previous NCT00938470 was an incorrect match.",
    },
    "HELP-ER": {
        "registry":            "GCIG/ENGOT",
        "registry_id":         "ENGOT-OV47",
        "registry_url":        "https://gcigtrials.org/clinical-trials/engot-ov47-noggo-tr2-help-er",
        "registry_confidence": "HIGH",
        "protocol_public":     False,
        "protocol_note":       "Registered with Gynecologic Cancer InterGroup (GCIG) as ENGOT-OV47/NOGGO TR2/HELP-ER. ENGOT protocols are not publicly available — access requires consortium membership.",
    },
    "CLL18 / MOIRAI": {
        "registry":            "EudraCT/CTIS",
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "HIGH",
        "protocol_public":     False,
        "protocol_note":       "Pan-European Phase III academic CLL trial. Regulatory approvals obtained in 13/16 countries as of late 2025. Will appear on EU CTIS or EudraCT imminently — check https://euclinicaltrials.eu periodically.",
    },
    "EMBT Registry": {
        "_clear_nct":          True,  # NCT01362985 is a related analysis study, not the registry itself
        "registry":            "EBMT",
        "registry_id":         None,
        "registry_url":        "https://www.ebmt.org/registry",
        "registry_confidence": "HIGH",
        "protocol_public":     False,
        "protocol_note":       "European Blood and Marrow Transplantation network's proprietary registry. Not on any public trial registry. Data access requires formal EBMT membership and data access agreement.",
    },
    "LOGGIC Core": {
        "registry":            "EudraCT",
        "registry_id":         None,
        "registry_url":        "https://www.clinicaltrialsregister.eu",
        "registry_confidence": "HIGH",
        "protocol_public":     False,
        "protocol_note":       "European paediatric low-grade glioma cooperative registry (SIOPE network). Registered on EudraCT, not CT.gov. Protocol access requires SIOPE/LOGGIC consortium membership.",
    },
    "SIOPE DIPG Registry": {
        "registry":            "EudraCT",
        "registry_id":         None,
        "registry_url":        "https://www.clinicaltrialsregister.eu",
        "registry_confidence": "HIGH",
        "protocol_public":     False,
        "protocol_note":       "SIOPE (European Society for Paediatric Oncology) DIPG/DMG registry. EudraCT registered. Protocol not publicly available.",
    },
    "ITCC 059": {
        "registry":            "EudraCT",
        "registry_id":         None,
        "registry_url":        "https://www.clinicaltrialsregister.eu",
        "registry_confidence": "MEDIUM",
        "protocol_public":     False,
        "protocol_note":       "ITCC European consortium trial. Inotuzumab ozogamicin in paediatric CD22+ ALL. Erasmus Medical Centre sponsor. Typically EudraCT-registered; no CT.gov entry found.",
    },

    # ── Genuinely unregistered ───────────────────────────────────────────────

    "GAMBIT": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Irish Cancer Society-funded investigator-initiated biomarker/sample collection study. PI: Prof Jarushka Naidoo, Beaumont RCSI. Biospecimen collection protocols are not routinely registered on public trial registries.",
    },
    "SLECT": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Tallaght University Hospital observational study of late effects in Irish testicular cancer survivors. PI: Dr Muhammad Raheel Khan. Not registered on any international registry.",
    },
    "Vulval Cancer: A Focus on Survivorship": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Cross-sectional QoL survey study in Irish vulval cancer survivors. Prof Donal Brennan / Dr Aisling McDonnell, UCD/Mater. Survey studies of this type are not routinely registered.",
    },
    "AFG Post-RT": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Mater Hospital pilot feasibility study of autologous fat grafting post-radiotherapy for vulval symptoms. PI: Prof Donal Brennan. Small Irish pilot — no public registry entry found.",
    },
    "Cell-free DNA": {
        "_clear_nct":          True,  # Previous match was wrong
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Irish in-house translational study of cell-free DNA in high-grade non-Hodgkin lymphoma with FDG PET-CT. Translational/sample collection — not publicly registered.",
    },
    "BD CHaPTeR": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Clinical Haematology Patients Tissue for Research — tissue biobank. Biobanks are not registerable as clinical trials. Access via formal data/tissue access agreement with hosting institution.",
    },
    "BD – Bone Marrow/Blood": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Bone marrow and blood sample collection from healthy volunteers for R&D purposes. Not a clinical trial — not registerable.",
    },
    "HRQOL": {
        "_clear_nct":          True,  # NCT07046481 was a wrong match
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Irish observational study of HRQOL impact of palliative/ablative radiotherapy in metastatic disease. PI: Prof Aisling Barry. Not registered on any public registry.",
    },
    "TAGNEY": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Cork University Hospital microbiome biomarker study. PI: Dr Brian Bird. Investigator-initiated biomarker protocol — not formally registered on any public registry.",
    },
    "NK-4-GBM": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "Trinity College Dublin translational NK cell study for glioblastoma. CTRIAL-IE 26-03. Early-phase translational — not a registerable clinical trial at this stage.",
    },
    "NBL NK Study (TCD)": {
        "registry":            None,
        "registry_id":         None,
        "registry_url":        None,
        "registry_confidence": "N/A",
        "protocol_public":     False,
        "protocol_note":       "TCD pre-clinical/translational study targeting NK cell metabolism for neuroblastoma. Not a registerable clinical trial.",
    },
}


def apply_updates(trials):
    for t in trials:
        name = t["name"]
        r = RESEARCH.get(name, {})

        # Clear wrong NCT matches first
        if r.get("_clear_nct"):
            t["clinicaltrials_gov_id"]  = None
            t["clinicaltrials_gov_url"] = None
        t.pop("nct_match_confidence", None)
        t.pop("euctr_id", None)
        t.pop("euctr_url", None)

        # Apply explicit research updates
        for field in ("clinicaltrials_gov_id", "clinicaltrials_gov_url",
                      "registry", "registry_id", "registry_url",
                      "registry_confidence", "protocol_public", "protocol_note",
                      "trial_status"):
            if field in r:
                t[field] = r[field]

        # ── Derive defaults for trials NOT in RESEARCH ─────────────────────
        if name not in RESEARCH:
            # Trials that had CT.gov IDs from the original scrape (not the enrichment script)
            if t.get("clinicaltrials_gov_id") and not t.get("registry"):
                t.setdefault("registry",            "ClinicalTrials.gov")
                t.setdefault("registry_id",         t["clinicaltrials_gov_id"])
                t.setdefault("registry_url",        t["clinicaltrials_gov_url"])
                t.setdefault("registry_confidence", "HIGH")
                t.setdefault("protocol_public",     True)
                t.setdefault("protocol_note",       "")
            elif not t.get("registry"):
                t.setdefault("registry",            None)
                t.setdefault("registry_id",         None)
                t.setdefault("registry_url",        None)
                t.setdefault("registry_confidence", "N/A")
                t.setdefault("protocol_public",     False)
                t.setdefault("protocol_note",       "")

        t.setdefault("trial_status", "Active")

    return trials


def save_json(trials):
    with open("data/trials.json", "w") as f:
        json.dump(trials, f, indent=2)
    print(f"data/trials.json: {len(trials)} trials written.")


def save_csv(trials):
    fieldnames = [
        "name", "number", "category", "type", "sponsor", "phase",
        "principal_investigator", "patient_population", "purpose", "sites",
        "full_title", "about",
        "recruitment_started_ireland", "recruitment_started_global",
        "global_target", "ireland_target",
        "registry", "registry_id", "registry_url", "registry_confidence",
        "clinicaltrials_gov_id", "clinicaltrials_gov_url",
        "protocol_public", "protocol_note", "trial_status",
        "url",
    ]
    with open("data/trials.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trials)
    print("data/trials.csv written.")


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
            scraped_date TEXT
        )
    """)
    today = date.today().isoformat()
    for t in trials:
        c.execute("""
            INSERT INTO trials VALUES
            (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t.get("name"), t.get("number"), t.get("category"), t.get("url"),
            t.get("full_title"), t.get("phase"), t.get("type"), t.get("sponsor"),
            t.get("principal_investigator"), t.get("patient_population"),
            t.get("purpose"), t.get("about"), t.get("sites"),
            t.get("recruitment_started_global"), t.get("recruitment_started_ireland"),
            t.get("global_target"), t.get("ireland_target"),
            t.get("clinicaltrials_gov_id"), t.get("clinicaltrials_gov_url"),
            t.get("registry"), t.get("registry_id"), t.get("registry_url"),
            t.get("registry_confidence"),
            1 if t.get("protocol_public") else 0,
            t.get("protocol_note"), t.get("trial_status"),
            today,
        ))
    conn.commit()
    conn.close()
    print("data/trials.db written.")


if __name__ == "__main__":
    with open("data/trials.json") as f:
        trials = json.load(f)

    trials = apply_updates(trials)
    save_json(trials)
    save_csv(trials)
    save_db(trials)

    # Quick summary
    by_reg = {}
    for t in trials:
        r = t.get("registry") or "None"
        by_reg[r] = by_reg.get(r, 0) + 1
    print("\nRegistry breakdown:")
    for k, v in sorted(by_reg.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    nct = sum(1 for t in trials if t.get("clinicaltrials_gov_id"))
    pub = sum(1 for t in trials if t.get("protocol_public"))
    term = sum(1 for t in trials if t.get("trial_status") == "TERMINATED")
    print(f"\nTrials with NCT ID:       {nct}/82")
    print(f"Trials with public protocol: {pub}/82")
    print(f"Terminated:               {term}/82")
