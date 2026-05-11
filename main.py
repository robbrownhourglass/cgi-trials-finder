import os, json, re
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ── Load trial data at startup ──
_root = Path(__file__).parent
with open(_root / "data" / "trials.json") as f:
    _raw = json.load(f)

TRIALS = {
    t["name"]: t for t in _raw
    if t.get("trial_status") != "TERMINATED"
}

CARD_FIELDS = (
    "name", "category", "url", "purpose", "about", "patient_population",
    "sites", "type", "phase", "sponsor",
    "clinicaltrials_gov_url", "registry_url",
    "eligibility_min_age", "eligibility_max_age",
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
    if (len(pool) <= 3 and n_asked > 0) or n_asked >= 3:
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

    return JSONResponse(result)


@app.get("/")
async def root():
    return FileResponse(_root / "src" / "patient-finder.html")
