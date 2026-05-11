import os, json, re
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# ── Load trial data at startup ──
_root = Path(__file__).parent
with open(_root / "data" / "trials.json") as f:
    _raw = json.load(f)

TRIALS = {
    t["name"]: t for t in _raw
    if t.get("trial_status") != "TERMINATED"
}

CARD_FIELDS = (
    "name", "number", "category", "url", "full_title",
    "purpose", "about", "patient_population",
    "principal_investigator", "type", "sponsor",
    "recruitment_started_ireland", "ireland_target",
    "clinicaltrials_gov_url", "registry_url",
    "eligibility_min_age", "eligibility_max_age", "eligibility_sex",
    "inclusion_criteria", "exclusion_criteria",
)

client = anthropic.Anthropic()


# ── Request model ──
class TurnRequest(BaseModel):
    category: str
    conversation: list[dict] = []
    remaining_names: list[str] | None = None


# ── Helpers ──
def trial_summary(t: dict) -> str:
    lines = [f"Trial: {t['name']}"]
    if t.get("patient_population"):
        lines.append(f"Population: {t['patient_population']}")
    incl = (t.get("inclusion_criteria") or [])[:6]
    excl = (t.get("exclusion_criteria") or [])[:4]
    if incl:
        lines.append("Inclusion: " + " | ".join(incl))
    if excl:
        lines.append("Exclusion: " + " | ".join(excl))
    if t.get("eligibility_min_age"):
        lines.append(f"Min age: {t['eligibility_min_age']}")
    if t.get("eligibility_max_age"):
        lines.append(f"Max age: {t['eligibility_max_age']}")
    sex = t.get("eligibility_sex")
    if sex and sex != "ALL":
        lines.append(f"Sex: {sex.title()} only")
    return "\n".join(lines)


def parse_claude_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def card_data(name: str) -> dict:
    t = TRIALS.get(name, {})
    return {k: t.get(k) for k in CARD_FIELDS}


# ── Main endpoint ──
@app.post("/next-question")
async def next_question(req: TurnRequest):
    if req.remaining_names is None:
        pool = [t for t in TRIALS.values() if t["category"] == req.category]
    else:
        pool = [TRIALS[n] for n in req.remaining_names if n in TRIALS]

    if not pool:
        return JSONResponse({"done": True, "remaining_names": [], "remaining_trials": []})

    n_asked = len(req.conversation)

    # Stop if small enough pool (after at least one question) or hit question limit
    if (len(pool) <= 1 and n_asked > 0) or n_asked >= 5:
        names = [t["name"] for t in pool]
        return JSONResponse({
            "done": True,
            "remaining_names": names,
            "remaining_trials": [card_data(n) for n in names],
        })

    trials_text = "\n\n".join(trial_summary(t) for t in pool)

    convo_text = ""
    if req.conversation:
        convo_text = "\n\nConversation so far:\n" + "\n".join(
            f"Q: {c['question']}\nA: {c['answer']}" for c in req.conversation
        )

    if n_asked == 0:
        filter_instruction = (
            "This is the first question — no filtering needed yet. "
            "Set remaining_names to all the trial names listed above."
        )
    else:
        last = req.conversation[-1]
        filter_instruction = (
            f'The patient just answered "{last["answer"]}" to: "{last["question"]}".\n'
            "Based on ALL answers so far, decide which trials to KEEP in remaining_names. "
            'If the patient said "Not sure" or "Prefer not to say" to any question, '
            "do not eliminate trials based on that answer."
        )

    prompt = f"""You are helping an Irish cancer patient find relevant clinical trials (Cancer Trials Ireland).
The patient has selected cancer type: {req.category}.

Trials under consideration ({len(pool)}):

{trials_text}
{convo_text}

{filter_instruction}

Then generate the next single most useful question to further narrow down the remaining trials.

Rules:
- Plain English only, no medical jargon
- Ask about things that genuinely distinguish these specific trials (e.g. treatment history, cancer subtype, biomarkers, prior therapies, age, sex)
- 2–4 answer options
- Always include "Not sure / prefer not to say" as the last option
- The question must be answerable by the patient without specialist knowledge
- NEVER ask about a topic or dimension already covered in the conversation above — even if the patient's answer was vague or unhelpful
- If the patient answered "Not sure / prefer not to say" (or equivalent) to a previous question, treat that entire topic as exhausted and ask about a completely different distinguishing factor
- Do not ask follow-up or clarifying questions on any topic where the patient already gave an answer

Return ONLY valid JSON, no other text:
{{
  "remaining_names": ["trial name 1", "trial name 2", ...],
  "done": false,
  "question": "Question text here?",
  "options": [{{"label": "Option A"}}, {{"label": "Option B"}}, {{"label": "Not sure / prefer not to say"}}]
}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_claude_json(response.content[0].text)

    # Validate names against current pool
    valid = {t["name"] for t in pool}
    result["remaining_names"] = [n for n in result.get("remaining_names", []) if n in valid]
    result["remaining_trials"] = [card_data(n) for n in result["remaining_names"]]

    # Stop immediately if the filtered pool is already small enough — no point asking more
    if len(result["remaining_names"]) <= 1:
        result["done"] = True
        result.pop("question", None)
        result.pop("options", None)

    return JSONResponse(result)


class CancerTypeRequest(BaseModel):
    typed: str

@app.post("/find-cancer-type")
async def find_cancer_type(req: CancerTypeRequest):
    categories = [
        "Breast", "Gastrointestinal", "Lung", "Skin Cancer",
        "Lymphoma & Blood Cancers", "Gynaecological", "Genitourinary",
        "Head & Neck", "Central Nervous System", "Sarcoma",
        "Paediatric", "Basket (Multiple Types)",
    ]
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        messages=[{"role": "user", "content":
            f'A patient described their cancer as: "{req.typed}"\n\n'
            f'Available categories: {", ".join(categories)}\n\n'
            'Return ONLY the exact category name that best matches. '
            'If it does not clearly match any category, return "unknown".'}],
    )
    cat = response.content[0].text.strip().strip('"')
    matched = next((c for c in categories if c.lower() == cat.lower()), None)
    return JSONResponse({"category": matched})


@app.get("/trials")
async def get_all_trials():
    trials = [{k: t.get(k) for k in CARD_FIELDS} for t in TRIALS.values()]
    return JSONResponse({"trials": trials})


@app.get("/trials/{category}")
async def get_trials_by_category(category: str):
    trials = [
        {k: t.get(k) for k in CARD_FIELDS}
        for t in TRIALS.values()
        if t["category"] == category
    ]
    return JSONResponse({"trials": trials})


class TrialChatRequest(BaseModel):
    trial_name: str
    conversation: list[dict] = []
    message: str


def trial_context(t: dict) -> str:
    lines = [
        f"Trial name: {t.get('name')}",
        f"Full title: {t.get('full_title')}",
        f"Category: {t.get('category')}",
        f"Type: {t.get('type')}",
        f"Sponsor: {t.get('sponsor')}",
        f"Principal investigator(s): {t.get('principal_investigator')}",
        f"Purpose: {t.get('purpose')}",
        f"About: {t.get('about')}",
        f"Patient population: {t.get('patient_population')}",
    ]
    if t.get("eligibility_min_age") or t.get("eligibility_max_age"):
        lines.append(f"Age eligibility: {t.get('eligibility_min_age', '?')} – {t.get('eligibility_max_age', '?')} years")
    if t.get("eligibility_sex") and t.get("eligibility_sex") != "ALL":
        lines.append(f"Sex: {t['eligibility_sex'].title()} only")
    incl = t.get("inclusion_criteria") or []
    excl = t.get("exclusion_criteria") or []
    if incl:
        lines.append("Inclusion criteria:\n" + "\n".join(f"  - {c}" for c in incl))
    if excl:
        lines.append("Exclusion criteria:\n" + "\n".join(f"  - {c}" for c in excl))
    if t.get("ireland_target"):
        lines.append(f"Ireland recruitment target: {t['ireland_target']} patients")
    if t.get("recruitment_started_ireland"):
        lines.append(f"Recruitment started in Ireland: {t['recruitment_started_ireland']}")
    if t.get("clinicaltrials_gov_url"):
        lines.append(f"ClinicalTrials.gov: {t['clinicaltrials_gov_url']}")
    if t.get("url"):
        lines.append(f"CTI page: {t['url']}")
    return "\n".join(l for l in lines if not l.endswith(": None") and not l.endswith(": "))


@app.post("/trial-chat")
async def trial_chat(req: TrialChatRequest):
    t = TRIALS.get(req.trial_name)
    if not t:
        return JSONResponse({"answer": "Sorry, I couldn't find that trial."})

    context = trial_context(t)

    system = (
        "You are a helpful assistant for Cancer Trials Ireland, answering questions about a specific clinical trial "
        "on behalf of a patient or their carer. Use only the trial information provided below — do not invent details. "
        "Answer in plain, warm English with no medical jargon. "
        "Do not use Markdown formatting — no headers, no bullet points, no asterisks. Write in flowing prose only. "
        "If the trial information doesn't cover the patient's question, "
        "say so honestly and suggest they speak with their oncologist or contact Cancer Trials Ireland directly.\n\n"
        f"TRIAL INFORMATION:\n{context}"
    )

    messages = []
    for turn in req.conversation:
        messages.append({"role": "user", "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["assistant"]})
    messages.append({"role": "user", "content": req.message})

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=system,
        messages=messages,
    )
    return JSONResponse({"answer": response.content[0].text.strip()})


@app.get("/")
async def root():
    return FileResponse(_root / "src" / "patient-finder.html")
