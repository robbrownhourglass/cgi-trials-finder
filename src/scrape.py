#!/usr/bin/env python3
"""
Cancer Trials Ireland — Trial Scraper
Scrapes all trial category pages and individual trial detail pages from cancertrials.ie

Usage:
    pip install requests beautifulsoup4
    python3 src/scrape.py

Output:
    data/trials.json   — full enriched trial data
    data/trials.csv    — flat CSV for spreadsheet use
    data/trials.db     — SQLite database
"""

import requests
from bs4 import BeautifulSoup
import json, re, sqlite3, csv, time
from datetime import date

CATEGORIES = {
    "Breast": "https://cancertrials.ie/current-trials/breast/",
    "Skin Cancer": "https://cancertrials.ie/current-trials/skin-cancer/",
    "Lung": "https://cancertrials.ie/current-trials/lung/",
    "Genitourinary": "https://cancertrials.ie/current-trials/genitourinary/",
    "Head & Neck": "https://cancertrials.ie/current-trials/head-neck/",
    "Paediatric": "https://cancertrials.ie/current-trials/paediatric/",
    "Central Nervous System": "https://cancertrials.ie/current-trials/central-nervous-system/",
    "Gastrointestinal": "https://cancertrials.ie/current-trials/gastrointestinal/",
    "Gynaecological": "https://cancertrials.ie/current-trials/gynaecological/",
    "Lymphoma & Blood Cancers": "https://cancertrials.ie/current-trials/lymphoma-blood-cancers/",
    "Sarcoma": "https://cancertrials.ie/current-trials/sarcoma/",
    "Basket (Multiple Types)": "https://cancertrials.ie/current-trials/baskettranslational/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Encoding": "identity",
}


def scrape_categories():
    """Scrape all category listing pages and return basic trial list."""
    trials = []

    for category, url in CATEGORIES.items():
        print(f"Fetching {category}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            cti_links = {
                a.get_text(strip=True): a["href"]
                for a in soup.find_all("a", href=True)
                if "/cti-trials/" in a["href"] and a.get_text(strip=True) != "Cancer Trials"
            }

            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                if not rows:
                    continue
                headers_row = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
                if "Name" not in headers_row:
                    continue

                for row in rows[1:]:
                    cells = row.find_all(["th", "td"])
                    if len(cells) < 4:
                        continue

                    name = cells[0].get_text(strip=True)
                    number = cells[1].get_text(strip=True)
                    patients = cells[2].get_text(strip=True)
                    purpose = cells[3].get_text(strip=True)
                    trial_url = cti_links.get(name)

                    if name not in [t["name"] for t in trials]:
                        trials.append({
                            "name": name,
                            "number": number,
                            "category": category,
                            "url": trial_url,
                            "patient_population": patients,
                            "purpose": purpose,
                        })
                        print(f"  ✓ {name} ({number})")

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(0.4)

    return trials


def scrape_detail(url):
    """Fetch and parse a single trial detail page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        detail = {
            "full_title": None,
            "principal_investigator": None,
            "type": None,
            "sponsor": None,
            "phase": None,
            "recruitment_started_global": None,
            "recruitment_started_ireland": None,
            "global_target": None,
            "ireland_target": None,
            "sites": None,
            "about": None,
            "clinicaltrials_gov_id": None,
            "clinicaltrials_gov_url": None,
        }

        content = soup.find("div", class_="entry-content") or soup.find("main") or soup
        lines = [l.strip() for l in content.get_text(separator="\n").split("\n") if l.strip()]

        label_map = {
            "Full Title:": "full_title",
            "Principal Investigator:": "principal_investigator",
            "Type:": "type",
            "Sponsor:": "sponsor",
            "Phase:": "phase",
            "Global Recruitment Target:": "global_target",
            "Ireland Recruitment Target:": "ireland_target",
        }

        for i, line in enumerate(lines):
            if line in label_map and i + 1 < len(lines):
                next_val = lines[i + 1]
                if not next_val.endswith(":") or len(next_val) > 30:
                    detail[label_map[line]] = next_val

            if line == "Recruitment Started:":
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].startswith("Global:"):
                        detail["recruitment_started_global"] = lines[j].replace("Global:", "").strip()
                    elif lines[j].startswith("Ireland:"):
                        detail["recruitment_started_ireland"] = lines[j].replace("Ireland:", "").strip()

            if "where's this trial being run" in line.lower() and i + 1 < len(lines):
                detail["sites"] = lines[i + 1]

            if line.lower() == "about this trial" and i + 1 < len(lines):
                detail["about"] = lines[i + 1]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "clinicaltrials.gov" in href:
                detail["clinicaltrials_gov_url"] = href
                nct = re.search(r"NCT\d+", href)
                if nct:
                    detail["clinicaltrials_gov_id"] = nct.group()

        if detail["type"] and detail["type"].endswith(":"):
            detail["type"] = None

        return detail

    except Exception as e:
        return {"error": str(e)}


def save_outputs(trials):
    """Write JSON, CSV, and SQLite outputs."""
    # JSON
    with open("data/trials.json", "w") as f:
        json.dump(trials, f, indent=2)

    # CSV
    fieldnames = [
        "name", "number", "category", "phase", "type", "sponsor",
        "principal_investigator", "patient_population", "purpose", "sites",
        "recruitment_started_ireland", "global_target", "ireland_target",
        "clinicaltrials_gov_id", "clinicaltrials_gov_url", "url",
    ]
    with open("data/trials.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trials)

    # SQLite
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
            scraped_date TEXT
        )
    """)
    today = date.today().isoformat()
    for t in trials:
        c.execute("""
            INSERT INTO trials VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            t.get("name"), t.get("number"), t.get("category"), t.get("url"),
            t.get("full_title"), t.get("phase"), t.get("type"), t.get("sponsor"),
            t.get("principal_investigator"), t.get("patient_population"),
            t.get("purpose"), t.get("about"), t.get("sites"),
            t.get("recruitment_started_global"), t.get("recruitment_started_ireland"),
            t.get("global_target"), t.get("ireland_target"),
            t.get("clinicaltrials_gov_id"), t.get("clinicaltrials_gov_url"),
            today,
        ))
    conn.commit()
    conn.close()

    print(f"\nSaved {len(trials)} trials to data/trials.json, data/trials.csv, data/trials.db")


if __name__ == "__main__":
    print("=== Cancer Trials Ireland Scraper ===\n")
    trials = scrape_categories()

    print(f"\nFetching detail pages for {len(trials)} trials...")
    for i, trial in enumerate(trials):
        if trial.get("url"):
            print(f"  [{i+1:02d}/{len(trials)}] {trial['name']}")
            detail = scrape_detail(trial["url"])
            trial.update(detail)
            time.sleep(0.3)

    save_outputs(trials)
    print("\nDone.")
