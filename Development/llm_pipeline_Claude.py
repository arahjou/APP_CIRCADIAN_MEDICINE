# =============================================================================
# Block I — Imports and project root
# =============================================================================
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

try:
    from langgraph.checkpoint.memory import InMemorySaver as MemorySaver
except Exception:
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except Exception:
        MemorySaver = None

# Walk up from cwd to find project root.
PROJECT_ROOT = Path.cwd()
for _ in range(6):
    if (PROJECT_ROOT / "tools" / "llm_conversation.py").exists():
        break
    PROJECT_ROOT = PROJECT_ROOT.parent
else:
    raise RuntimeError("Could not locate project root containing tools/llm_conversation.py")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools.llm_conversation as _lc
from tools.llm_conversation import (
    _compact_report_for_llm,
    _parse_structured_queries,
    _sanitize_pmids,
)
from tools.pubmed_search import RetrievalConfig, evidence_to_text, search_pubmed

print("Imports OK")
print("Project root:", PROJECT_ROOT)
print("Available Ollama models:")
try:
    print(subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout)
except Exception as exc:
    print(f"Could not list Ollama models: {exc}")


# =============================================================================
# Block II — Configuration
# =============================================================================
DB_PATH = PROJECT_ROOT / "Actigraph_record.db"
AUDIENCE: Literal["expert", "doctor", "layperson"] = "doctor"
ANAMNESIS = ""  # set to patient history/symptoms to activate symptom_metric_linker

# Optional: pick a specific database row. If None, the notebook uses the latest row.
ROW_KEY: tuple[str, str, str] | None = None
# ROW_KEY = ("admin", "ID-001", "ID-002")

AGENT_CONFIG = {
    "data_summariser": {
        "model": "qwen3.5:4b",
        "temperature": 0.2,
        "role": "clinical metric summariser",
    },
    "pubmed_query_planner": {
        "model": "llama3.2:latest",
        "fallback_model": "phi4:14b",
        "temperature": 0.1,
        "role": "research query planner",
    },
    "relevance_judge": {
        "model": "qwen3.5:4b",
        "fallback_model": "phi4:14b",
        "temperature": 0.0,
        "role": "evidence filter / evaluator",
    },
    "literature_synthesiser": {
        # Heavier model for narrative quality — synthesis is where the "robotic"
        # feel comes from on small models.
        "model": "phi4:14b",
        "fallback_model": "qwen3.5:4b",
        "temperature": 0.2,
        "role": "literature synthesis agent",
    },
    "symptom_metric_linker": {
        "model": "qwen3.5:4b",
        "temperature": 0.1,
        "role": "symptom-to-metric mapper",
    },
    "report_writer": {
        # Heavier model + low temperature for the final clinical narrative.
        "model": "phi4:14b",
        "fallback_model": "qwen3.5:4b",
        "temperature": 0.1,
        "role": "audience-aware report writer",
    },
}

# Wider retrieval — the relevance judge now scores and ranks, so we can afford
# to pull more candidates and let it earn its keep.
RETRIEVAL_CFG = RetrievalConfig(
    retmax_per_query=30,
    keep_per_query=10,
    max_total_items=50,
    years_back=10,
    humans_only=True,
    adults_only=(AUDIENCE == "doctor"),
)

# How many of the top-scored evidence items to keep after the relevance judge.
KEEP_TOP_N_AFTER_JUDGING = 15

# How many constructs to drive query planning and synthesis from. More = broader
# but more tokens and slower.
MAX_CONSTRUCTS = 6

# Z-score threshold for flagging a metric as "changed" enough to drive a query.
# Tune this to your report's effect-size convention.
CONSTRUCT_Z_THRESHOLD = 1.0

# Persistent notebook memory: stores successful tuning notes across sessions.
USE_TUNING_MEMORY = True
MEMORY_PATH = PROJECT_ROOT / "Development" / "llm_pipeline_tuning_memory.json"

# LangGraph short-term checkpointing.
THREAD_ID = "llm-pipeline-tuning"

for node, cfg in AGENT_CONFIG.items():
    fallback = f" fallback={cfg['fallback_model']}" if "fallback_model" in cfg else ""
    print(f"{node:24} model={cfg['model']} temp={cfg['temperature']}{fallback}")


# =============================================================================
# Block III — Load report from DB
# =============================================================================
con = sqlite3.connect(DB_PATH)
rows = con.execute(
    "SELECT username, period_id_1, period_id_2, audience, model, created_at "
    "FROM ai_analysis_runs ORDER BY created_at DESC"
).fetchall()
print(f"Available rows: {len(rows)}")
for r in rows[:20]:
    print(
        f"  username={r[0]:<10} P1={r[1]:<10} P2={r[2]:<10} "
        f"audience={r[3]:<10} model={r[4]:<14} created={r[5]}"
    )

if not rows:
    raise RuntimeError("No rows found in ai_analysis_runs")

if ROW_KEY is None:
    ROW_KEY = (rows[0][0], rows[0][1], rows[0][2])
print(f"\nSelected: username={ROW_KEY[0]} P1={ROW_KEY[1]} P2={ROW_KEY[2]}")

raw = con.execute(
    "SELECT json_input FROM ai_analysis_runs "
    "WHERE username=? AND period_id_1=? AND period_id_2=? "
    "ORDER BY created_at DESC LIMIT 1",
    ROW_KEY,
).fetchone()
con.close()
if not raw or not raw[0]:
    raise RuntimeError(f"No json_input found for {ROW_KEY}")

report_data = json.loads(raw[0])
compact_report = _compact_report_for_llm(report_data)
print(f"compact_report chars: {len(compact_report)}")
print(compact_report[:1500])


# =============================================================================
# Block IV — Construct mapping (deterministic, no LLM)
# =============================================================================
# Maps each metric to (construct_when_decreased, construct_when_increased).
# Construct phrases are clinical concepts suitable for PubMed — never algorithm
# acronyms. Extend as your report grows.
METRIC_CONSTRUCT_MAP: dict[str, tuple[str, str]] = {
    # Regularity / circadian shape
    "SRI":         ("sleep irregularity",                  "sleep regularity"),
    "IS":          ("circadian rhythm fragmentation",      "circadian stability"),
    "IV":          ("circadian rhythm stability",          "intradaily variability fragmentation"),
    "RA":          ("dampened circadian amplitude",        "robust circadian rhythm"),
    "L5":          ("restless nighttime activity",         "consolidated rest period"),
    "M10":         ("low daytime activity",                "high daytime activity"),
    # Sleep quantity / quality
    "TST":         ("short sleep duration",                "long sleep duration"),
    "SE":          ("poor sleep efficiency",               "high sleep efficiency"),
    "WASO":        ("fragmented sleep",                    "consolidated sleep"),
    "SOL":         ("prolonged sleep onset latency",       "rapid sleep onset"),
    # Phase
    "midsleep":    ("advanced sleep phase",                "delayed sleep phase"),
    "onset":       ("advanced sleep onset",                "delayed sleep onset"),
    "offset":      ("early wake time",                     "late wake time"),
    "CPD":         ("circadian phase disruption",          "circadian phase disruption"),
    # Cosinor
    "amplitude":   ("dampened circadian amplitude",        "elevated circadian amplitude"),
    "acrophase":   ("phase advance",                       "phase delay"),
    "mesor":       ("low activity baseline",               "elevated activity baseline"),
}


def _extract_metric_changes(report_data: dict) -> list[dict]:
    """
    Walk the report dict and pull out (metric, delta_z) pairs.

    This is intentionally permissive about field names because actigraphy
    reports vary. Adapt the keys below to your structure if needed.
    """
    candidates: list[dict] = []

    metrics_block = report_data.get("metrics") or report_data.get("comparison") or {}
    if isinstance(metrics_block, dict):
        for name, payload in metrics_block.items():
            if not isinstance(payload, dict):
                continue
            # Try several common field names for effect size / change.
            delta_z = (
                payload.get("delta_z")
                or payload.get("z")
                or payload.get("z_score")
                or payload.get("effect_size")
            )
            if delta_z is None:
                # Fallback: derive from p1/p2 if both present.
                p1 = payload.get("period1") or payload.get("p1")
                p2 = payload.get("period2") or payload.get("p2")
                if isinstance(p1, (int, float)) and isinstance(p2, (int, float)) and p1 != 0:
                    # Crude: use relative change as a proxy. Replace with your own logic if you have SDs.
                    delta_z = (p2 - p1) / max(abs(p1), 1e-6)
            if isinstance(delta_z, (int, float)):
                candidates.append({"metric": name, "delta_z": float(delta_z)})

    return candidates


def derive_constructs(report_data: dict, *, z_threshold: float = CONSTRUCT_Z_THRESHOLD) -> list[dict]:
    """
    Translate flagged metric changes into clinical constructs with direction.
    Returns list sorted by magnitude desc.
    """
    out: list[dict] = []
    for change in _extract_metric_changes(report_data):
        delta_z = change["delta_z"]
        if abs(delta_z) < z_threshold:
            continue
        metric_name = change["metric"]
        # Strip suffixes like "_p1", "_period2", "_diff".
        key = re.split(r"[_\-\s]", metric_name)[0]
        if key not in METRIC_CONSTRUCT_MAP:
            # Try case-insensitive match.
            for canon in METRIC_CONSTRUCT_MAP:
                if canon.lower() == key.lower():
                    key = canon
                    break
            else:
                continue
        down, up = METRIC_CONSTRUCT_MAP[key]
        construct = down if delta_z < 0 else up
        out.append({
            "metric": metric_name,
            "direction": "decreased" if delta_z < 0 else "increased",
            "magnitude_z": round(delta_z, 2),
            "construct": construct,
        })
    out.sort(key=lambda x: abs(x["magnitude_z"]), reverse=True)
    return out


# =============================================================================
# Block V — Prompts
# =============================================================================
# Reuse the existing summariser/anamnesis/audience prompts; override the ones
# we want to change.
AGENT1_SYSTEM = _lc._AGENT1_SYSTEM
AGENT2_ANAMNESIS_ADDENDUM = _lc._AGENT2_ANAMNESIS_ADDENDUM
AGENT6_SYSTEM = _lc._AGENT6_SYSTEM
AGENT5_AUDIENCES = dict(_lc._AGENT5_AUDIENCES)

# --- Construct-anchored query planner ----------------------------------------
AGENT2_SYSTEM = """You are a research query planner for clinical actigraphy reports.
You receive a list of CLINICAL CONSTRUCTS (e.g., "sleep irregularity", "delayed sleep phase")
that were derived from this patient's metric changes.

Your job: produce ONE PubMed query intent per construct.

Hard rules:
- Search for the CLINICAL CONSTRUCT and its health/behavioural correlates.
- NEVER use algorithm acronyms (SRI, IS, IV, L5, M10, RA, MESOR, etc.) in the query.
  Example: SRI decreased → search "sleep irregularity" + outcomes,
           NOT "sleep regularity index".
- Each query should target a meaningful CLINICAL OUTCOME: cardiometabolic risk,
  mood/depression, cognition, mortality, glycaemic control, etc. — not just descriptive.
- Population should match audience (adults for doctor reports).

Output: JSON lines, one object per query, with fields:
  topic        — the construct phrase, possibly with a co-term
  population   — e.g. "adults", "humans"
  context      — the outcome domain (e.g. "cardiometabolic outcomes")
  expected_link — short hypothesis sentence
"""

# --- Scored relevance judge --------------------------------------------------
RELEVANCE_SYSTEM = """You are an evidence filter for a clinical actigraphy report.

For EACH abstract, score 0–3 on three axes:
- construct_match: does it study the clinical construct (not just mention the metric)?
- outcome_relevance: does it link the construct to a meaningful health/behaviour outcome?
- study_quality: meta-analysis or RCT = 3; large prospective cohort = 2;
                 small or cross-sectional = 1; case report / opinion = 0.

Also extract a one_line_finding (≤ 20 words) capturing the abstract's clinical
take-home — what the construct predicts/causes/correlates with.

Output JSON ONLY, exactly this shape:
{"scored": [
  {"pmid": "...", "construct_match": 0-3, "outcome_relevance": 0-3,
   "study_quality": 0-3, "one_line_finding": "..."},
  ...
]}

Score honestly. Do not inflate to keep papers. Abstracts that only mention the
metric in passing without studying it should get construct_match = 0.
"""

# --- Per-construct synthesis -------------------------------------------------
AGENT4_SYSTEM = """You are a clinical literature synthesiser writing for a busy doctor.

You receive a list of CLINICAL CONSTRUCTS (each tied to a metric change in this patient)
with matched PubMed evidence for each.

For EACH construct, write ONE short paragraph (max 60 words) that:
1. States what the metric change indicates in plain clinical language.
2. Cites 1–3 PMIDs for what the literature links that construct to
   (outcomes, mechanisms, prognosis).
3. Uses concrete clinical framing — what does this mean for the patient?

Hard rules:
- ONE paragraph per construct. No more.
- Format each paragraph as: **Construct name** — paragraph text (PMID xxxxxxxx).
- Do NOT produce a generic "literature has shown..." summary.
- Do NOT repeat raw metric values; the doctor already has them.
- Do NOT hedge with "may/could/might" more than once per paragraph.
- If no evidence is matched for a construct, write:
  **Construct name** — (no direct evidence retrieved; clinical interpretation only).
"""

# --- Audience prompts (overwrite the doctor and patient versions) ------------
AGENT5_AUDIENCES["doctor"] = """You write clinical actigraphy reports for primary care
and sleep physicians.

Hard constraints:
- TOTAL length: 250–350 words. Not a word more. The doctor has 3 minutes.
- Use these exact section headers and order:

## Findings
Bullet list. Each bullet = one metric change + its clinical meaning + PMID citation.
Maximum 5 bullets. Format: "- **Metric** [direction]: clinical meaning (PMID xxxxxxxx)."

## Clinical Interpretation
2–3 sentences integrating the findings into a coherent picture
(e.g., "phase delay with reduced regularity suggests social jetlag pattern").
No bullet points here — prose.

## Suggested Next Steps
2–3 bullets. Concrete and actionable: lab tests, sleep diary, light hygiene,
chronotherapy, referral to sleep medicine. No platitudes ("consider lifestyle changes").

Hard rules:
- Cite PMIDs ONLY from Evidence Items provided. Format: (PMID 12345678).
- Never invent or guess a PMID. If unsure, omit the citation.
- Do not restate raw numbers the doctor sees in the metric chart.
- Use "may/could/might" at most TWICE in the whole report.
- No introductory paragraph. No closing summary. Start directly with `## Findings`.
"""

AGENT5_AUDIENCES["layperson"] = """You write actigraphy reports for patients with no
medical training.

Hard constraints:
- TOTAL length: 150–220 words. Patients won't read more.
- Use these exact section headers:

## What we found
2–3 short bullets. Plain language only. No acronyms. No PMIDs.
Example: "- Your sleep timing shifted later by about an hour."

## What this means for you
2–4 sentences. Concrete and reassuring where appropriate. No jargon.

## What to try
2–3 bullets. Practical actions a patient can do this week
(consistent wake time, morning light, avoid late caffeine).

## Sources
List PMID URLs only here, at the end. Do NOT cite PMIDs in the body.

Hard rules:
- No medical jargon. If you must use a term, define it in plain English.
- No fear-mongering. Frame findings as patterns, not diagnoses.
- No introductory paragraph. Start with `## What we found`.
"""


# =============================================================================
# Block VI — Pipeline state and helpers
# =============================================================================
class PipelineState(TypedDict, total=False):
    compact_report: str
    audience: str
    anamnesis: str
    tuning_memory: str
    data_summary: str
    constructs: list[dict]
    search_queries: list[dict]
    evidence_items: list[dict]
    raw_abstracts: str
    pmid_list: list[str]
    score_by_pmid: dict[str, int]
    lit_summary: str
    symptom_metric_table: str
    final_report: str
    claim_to_pmid_map: dict[str, list[str]]
    trace: list[dict[str, Any]]
    errors: list[str]


def load_tuning_memory() -> str:
    if not USE_TUNING_MEMORY or not MEMORY_PATH.exists():
        return ""
    try:
        data = json.loads(MEMORY_PATH.read_text())
        notes = data.get("notes", []) if isinstance(data, dict) else []
        return "\n".join(f"- {note}" for note in notes[-12:])
    except Exception as exc:
        return f"Memory read failed: {exc}"


def save_tuning_memory(note: str) -> None:
    if not USE_TUNING_MEMORY or not note.strip():
        return
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"notes": []}
    if MEMORY_PATH.exists():
        try:
            loaded = json.loads(MEMORY_PATH.read_text())
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass
    notes = list(data.get("notes", []))
    notes.append(note.strip())
    data["notes"] = notes[-50:]
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    MEMORY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def add_trace(state: PipelineState, node: str, output_summary: str) -> list[dict[str, Any]]:
    trace = list(state.get("trace", []))
    trace.append({
        "node": node,
        "model": AGENT_CONFIG.get(node, {}).get("model"),
        "output": output_summary,
    })
    return trace


def chat_node(node: str, system: str, user: str, *, json_mode: bool = False) -> str:
    cfg = AGENT_CONFIG[node]
    model_names = [cfg["model"]]
    if cfg.get("fallback_model") and cfg["fallback_model"] not in model_names:
        model_names.append(cfg["fallback_model"])

    last_error: Exception | None = None
    for model_name in model_names:
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "temperature": cfg.get("temperature", 0.2),
            }
            if json_mode:
                kwargs["format"] = "json"
            llm = ChatOllama(**kwargs)
            response = llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=user),
            ])
            content = response.content
            return content.strip() if isinstance(content, str) else str(content).strip()
        except Exception as exc:
            last_error = exc
            print(f"{node}: model {model_name} failed: {exc!r}")
    raise RuntimeError(f"{node} failed for all configured models") from last_error


def parse_scored_relevance(raw: str) -> list[dict]:
    """Parse the relevance judge's JSON output into a list of score dicts."""
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []
    if isinstance(parsed, dict):
        return parsed.get("scored") or []
    if isinstance(parsed, list):
        return parsed
    return []


def print_state_keys(state: PipelineState) -> None:
    keys = [
        "data_summary", "constructs", "search_queries", "pmid_list",
        "lit_summary", "symptom_metric_table", "final_report",
    ]
    for key in keys:
        value = state.get(key)
        if isinstance(value, str):
            print(f"{key:22} {len(value):5} chars")
        elif isinstance(value, list):
            print(f"{key:22} {len(value):5} items")
        elif isinstance(value, dict):
            print(f"{key:22} {len(value):5} keys")
        else:
            print(f"{key:22} {type(value).__name__}")


# =============================================================================
# Block VII — Pipeline nodes
# =============================================================================
def data_summariser(state: PipelineState) -> PipelineState:
    user = (
        f"# Actigraphy Metrics\n{state['compact_report']}\n\n"
        "Summarise these metrics for a downstream literature researcher. "
        "Be explicit about the DIRECTION of every meaningful change "
        "(e.g., 'SRI decreased by 17 points', 'midsleep shifted 1.2 h later'). "
        "Direction matters more than absolute values."
    )
    summary = chat_node("data_summariser", AGENT1_SYSTEM, user)
    return {
        **state,
        "data_summary": summary,
        "trace": add_trace(state, "data_summariser", f"{len(summary)} chars"),
    }


def construct_mapper(state: PipelineState) -> PipelineState:
    """Deterministically translate metric changes into clinical constructs."""
    constructs = derive_constructs(report_data, z_threshold=CONSTRUCT_Z_THRESHOLD)
    summary = "; ".join(
        f"{c['metric']} {c['direction']} → {c['construct']}"
        for c in constructs[:8]
    )
    return {
        **state,
        "constructs": constructs,
        "trace": add_trace(state, "construct_mapper", summary or "no salient changes detected"),
    }


def pubmed_query_planner(state: PipelineState) -> PipelineState:
    constructs = state.get("constructs", [])

    if not constructs:
        # Last-resort fallback if no salient changes were detected.
        constructs = [{
            "metric": "general",
            "direction": "any",
            "magnitude_z": 0.0,
            "construct": "circadian rhythm sleep wake disorder",
        }]

    top = constructs[:MAX_CONSTRUCTS]
    construct_block = "\n".join(
        f"- {c['metric']} {c['direction']} (z={c.get('magnitude_z', '?')}) "
        f"→ construct: {c['construct']}"
        for c in top
    )

    pop = "adults" if state.get("audience") == "doctor" else "humans"
    user = (
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Detected metric changes mapped to clinical constructs\n{construct_block}\n\n"
        f"Generate ONE PubMed query intent per construct above (target population: {pop}).\n"
        "Each query must target the CLINICAL CONSTRUCT and a meaningful health outcome — "
        "NOT the metric acronym. Output JSON lines, one object per query.\n"
    )
    if state.get("anamnesis", "").strip():
        user += "\n" + AGENT2_ANAMNESIS_ADDENDUM.format(anamnesis=state["anamnesis"])

    raw = chat_node("pubmed_query_planner", AGENT2_SYSTEM, user)
    queries = _parse_structured_queries(raw)

    if not queries:
        # Construct-driven fallback (much better than the old generic one).
        queries = [{
            "topic": c["construct"],
            "population": pop,
            "context": "health outcomes",
            "expected_link": f"{c['construct']} and clinical outcomes",
        } for c in top]

    return {
        **state,
        "search_queries": queries,
        "trace": add_trace(
            state, "pubmed_query_planner",
            f"{len(queries)} construct-anchored queries",
        ),
    }


def pubmed_retriever(state: PipelineState) -> PipelineState:
    items = search_pubmed(state.get("search_queries", []), config=RETRIEVAL_CFG)
    pmids = [str(x.get("pmid")) for x in items if x.get("pmid")]
    return {
        **state,
        "evidence_items": items,
        "pmid_list": pmids,
        "raw_abstracts": evidence_to_text(items),
        "trace": add_trace(state, "pubmed_retriever", f"{len(items)} evidence items"),
    }


def relevance_judge(state: PipelineState) -> PipelineState:
    items = state.get("evidence_items", [])
    if not items:
        return {**state, "trace": add_trace(state, "relevance_judge", "skipped; no evidence")}

    constructs = state.get("constructs", [])[:MAX_CONSTRUCTS]
    construct_text = "\n".join(
        f"- {c['construct']} ({c['direction']}, from {c['metric']})"
        for c in constructs
    ) or "- (no constructs derived)"

    user = (
        f"Clinical constructs to match against:\n{construct_text}\n\n"
        f"Evidence items:\n{json.dumps(items, ensure_ascii=False)}"
    )
    raw = chat_node("relevance_judge", RELEVANCE_SYSTEM, user, json_mode=True)
    scored = parse_scored_relevance(raw)

    score_by_pmid: dict[str, int] = {}
    finding_by_pmid: dict[str, str] = {}
    for s in scored:
        pmid = str(s.get("pmid", "")).strip()
        if not pmid:
            continue
        # Weighted score: construct match dominates.
        score_by_pmid[pmid] = (
            int(s.get("construct_match", 0)) * 2
            + int(s.get("outcome_relevance", 0))
            + int(s.get("study_quality", 0))
        )
        finding_by_pmid[pmid] = (s.get("one_line_finding") or "").strip()

    # Drop anything the judge gave construct_match = 0 (score will be ≤ 3 from
    # outcome+quality alone), keep only items with a positive construct match.
    def passes(item: dict) -> bool:
        pmid = str(item.get("pmid", ""))
        # We approximate "construct_match > 0" by requiring the score to be
        # at least 2 (since construct_match is doubled).
        return score_by_pmid.get(pmid, 0) >= 2

    filtered = [x for x in items if passes(x)]
    filtered.sort(
        key=lambda x: score_by_pmid.get(str(x.get("pmid")), 0),
        reverse=True,
    )
    filtered = filtered[:KEEP_TOP_N_AFTER_JUDGING]

    # Attach the one-line finding so the synthesiser can use it directly.
    for x in filtered:
        x["one_line_finding"] = finding_by_pmid.get(str(x.get("pmid")), "")

    pmids = [str(x.get("pmid")) for x in filtered if x.get("pmid")]
    return {
        **state,
        "evidence_items": filtered,
        "pmid_list": pmids,
        "raw_abstracts": evidence_to_text(filtered),
        "score_by_pmid": score_by_pmid,
        "trace": add_trace(
            state, "relevance_judge",
            f"kept {len(filtered)} of {len(scored)} scored (from {len(items)} retrieved)",
        ),
    }


def _match_evidence_to_construct(items: list[dict], construct: str, k: int = 5) -> list[dict]:
    """Crude keyword match between abstract text and construct phrase."""
    keywords = [w for w in re.split(r"\W+", construct.lower()) if len(w) > 3]
    if not keywords:
        return items[:k]

    scored: list[tuple[int, dict]] = []
    for x in items:
        text = (str(x.get("title", "")) + " " + str(x.get("abstract", ""))).lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((hits, x))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [x for _, x in scored[:k]]


def literature_synthesiser(state: PipelineState) -> PipelineState:
    constructs = state.get("constructs", [])[:MAX_CONSTRUCTS]
    items = state.get("evidence_items", [])

    if not constructs:
        # No constructs — fall back to a brief generic synthesis.
        user = (
            f"# Clinical Data Summary\n{state['data_summary']}\n\n"
            f"# PubMed Abstracts\n{state['raw_abstracts']}\n\n"
            "Write at most 3 short paragraphs of clinical synthesis."
        )
        summary = chat_node("literature_synthesiser", AGENT4_SYSTEM, user)
        return {
            **state,
            "lit_summary": summary,
            "trace": add_trace(state, "literature_synthesiser", f"{len(summary)} chars (no constructs)"),
        }

    # Build per-construct evidence packs so the LLM doesn't have to do the matching.
    construct_blocks: list[str] = []
    for c in constructs:
        relevant = _match_evidence_to_construct(items, c["construct"], k=5)
        block = (
            f"## {c['construct']} "
            f"({c['metric']} {c['direction']}, z={c.get('magnitude_z', '?')})\n"
        )
        if relevant:
            for x in relevant:
                finding = x.get("one_line_finding") or x.get("title", "")
                block += f"- PMID {x['pmid']}: {finding}\n"
        else:
            block += "- (no matched evidence)\n"
        construct_blocks.append(block)

    user = (
        "# Constructs and matched evidence\n\n"
        + "\n".join(construct_blocks)
        + "\n\nWrite ONE short paragraph per construct, following the system prompt exactly."
    )
    summary = chat_node("literature_synthesiser", AGENT4_SYSTEM, user)
    return {
        **state,
        "lit_summary": summary,
        "trace": add_trace(state, "literature_synthesiser", f"{len(summary)} chars"),
    }


def symptom_metric_linker(state: PipelineState) -> PipelineState:
    user = (
        f"# Patient Anamnesis\n{state.get('anamnesis', '')}\n\n"
        f"# Clinical Data Summary\n{state.get('data_summary', '')}\n\n"
        f"# Constructs\n"
        + "\n".join(
            f"- {c['construct']} ({c['direction']}, from {c['metric']})"
            for c in state.get("constructs", [])[:MAX_CONSTRUCTS]
        )
        + f"\n\n# PubMed Abstracts\n{state.get('raw_abstracts', '')}\n\n"
        "Produce the Symptom-Metric Correlation Table as instructed."
    )
    table = chat_node("symptom_metric_linker", AGENT6_SYSTEM, user)
    return {
        **state,
        "symptom_metric_table": table,
        "trace": add_trace(state, "symptom_metric_linker", f"{len(table)} chars"),
    }


def report_writer(state: PipelineState) -> PipelineState:
    audience = state.get("audience", "layperson")
    system_prompt = AGENT5_AUDIENCES.get(audience, AGENT5_AUDIENCES["layperson"])
    evidence_items = state.get("evidence_items", [])
    has_evidence = bool(evidence_items)

    constructs = state.get("constructs", [])[:MAX_CONSTRUCTS]
    construct_block = "\n".join(
        f"- {c['metric']} {c['direction']} (z={c.get('magnitude_z', '?')}) → {c['construct']}"
        for c in constructs
    ) or "(no salient changes detected)"

    user = (
        f"# Constructs (metric → clinical meaning)\n{construct_block}\n\n"
        f"# Per-construct literature synthesis\n{state.get('lit_summary', '')}\n\n"
        f"# Evidence Items (cite PMIDs ONLY from this list)\n"
        f"{json.dumps(evidence_items, ensure_ascii=False)}\n\n"
    )
    if state.get("symptom_metric_table", "").strip():
        user += (
            f"# Symptom-Metric Correlation\n{state['symptom_metric_table']}\n\n"
            "Add a `## Symptom-Metric Correlation` section after Clinical Interpretation.\n\n"
        )
    if has_evidence:
        user += (
            "Write the final report now, following the system prompt's structure and "
            "length budget exactly. Cite real PMIDs only. Never invent."
        )
    else:
        user += (
            "Write the final report now. No PubMed evidence was retrieved; do not cite PMIDs. "
            "Mark unsupported claims as '(no direct evidence found)'."
        )

    report = chat_node("report_writer", system_prompt, user)
    allowed = {str(p) for p in state.get("pmid_list", [])}
    report = _sanitize_pmids(report, allowed)

    claim_map: dict[str, list[str]] = {}
    for line in report.splitlines():
        cited = [p for p in re.findall(r"PMID\s*[:#-]?\s*(\d+)", line) if p in allowed]
        if cited:
            claim_map[line.strip()[:180]] = cited

    if allowed and audience != "layperson":
        # For doctor/expert reports, append references at the end.
        # (Layperson prompt already specifies a `## Sources` section.)
        refs = ["\n\n---\nReferences (PubMed):"]
        for i, pmid in enumerate(state.get("pmid_list", []), start=1):
            refs.append(f"{i}. PMID {pmid} — https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        report += "\n".join(refs)

    return {
        **state,
        "final_report": report,
        "claim_to_pmid_map": claim_map,
        "trace": add_trace(state, "report_writer", f"{len(report)} chars"),
    }


def tuning_memory_writer(state: PipelineState) -> PipelineState:
    note = (
        f"audience={state.get('audience')} | "
        f"constructs={len(state.get('constructs', []))} | "
        f"queries={len(state.get('search_queries', []))} | "
        f"kept_pmids={len(state.get('pmid_list', []))} | "
        f"models=" + ", ".join(f"{k}:{v['model']}" for k, v in AGENT_CONFIG.items())
    )
    save_tuning_memory(note)
    return {**state, "trace": add_trace(state, "tuning_memory_writer", "saved tuning note")}


def route_after_synthesis(state: PipelineState) -> str:
    return "symptom_metric_linker" if state.get("anamnesis", "").strip() else "report_writer"


# =============================================================================
# Block VIII — Build graph
# =============================================================================
def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("data_summariser", data_summariser)
    graph.add_node("construct_mapper", construct_mapper)
    graph.add_node("pubmed_query_planner", pubmed_query_planner)
    graph.add_node("pubmed_retriever", pubmed_retriever)
    graph.add_node("relevance_judge", relevance_judge)
    graph.add_node("literature_synthesiser", literature_synthesiser)
    graph.add_node("symptom_metric_linker", symptom_metric_linker)
    graph.add_node("report_writer", report_writer)
    graph.add_node("tuning_memory_writer", tuning_memory_writer)

    graph.set_entry_point("data_summariser")
    graph.add_edge("data_summariser", "construct_mapper")
    graph.add_edge("construct_mapper", "pubmed_query_planner")
    graph.add_edge("pubmed_query_planner", "pubmed_retriever")
    graph.add_edge("pubmed_retriever", "relevance_judge")
    graph.add_edge("relevance_judge", "literature_synthesiser")
    graph.add_conditional_edges(
        "literature_synthesiser",
        route_after_synthesis,
        {
            "symptom_metric_linker": "symptom_metric_linker",
            "report_writer": "report_writer",
        },
    )
    graph.add_edge("symptom_metric_linker", "report_writer")
    graph.add_edge("report_writer", "tuning_memory_writer")
    graph.add_edge("tuning_memory_writer", END)

    if MemorySaver is not None:
        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()


AGENT_GRAPH = build_graph()
print("LangGraph compiled")
print("Nodes:", [
    "data_summariser", "construct_mapper", "pubmed_query_planner",
    "pubmed_retriever", "relevance_judge", "literature_synthesiser",
    "symptom_metric_linker", "report_writer", "tuning_memory_writer",
])
print("Checkpointing:", "MemorySaver" if MemorySaver is not None else "not available")


# =============================================================================
# Block IX — Run
# =============================================================================
initial_state: PipelineState = {
    "compact_report": compact_report,
    "audience": AUDIENCE,
    "anamnesis": ANAMNESIS.strip(),
    "tuning_memory": load_tuning_memory(),
    "data_summary": "",
    "constructs": [],
    "search_queries": [],
    "evidence_items": [],
    "raw_abstracts": "",
    "pmid_list": [],
    "score_by_pmid": {},
    "lit_summary": "",
    "symptom_metric_table": "",
    "final_report": "",
    "claim_to_pmid_map": {},
    "trace": [],
    "errors": [],
}

run_config = {"configurable": {"thread_id": THREAD_ID}}

t0 = time.time()
try:
    final_state = AGENT_GRAPH.invoke(initial_state, config=run_config)
except TypeError:
    final_state = AGENT_GRAPH.invoke(initial_state)

print(f"Graph finished in {time.time() - t0:.1f}s")
print_state_keys(final_state)
print("\nTrace:")
for step in final_state.get("trace", []):
    print(f"- {step['node']}: {step['output']} [{step.get('model')}]")


# =============================================================================
# Block X — Inspect outputs
# =============================================================================
print("# Data Summary\n")
print(final_state.get("data_summary", ""))

print("\n# Constructs (metric → clinical construct)\n")
for c in final_state.get("constructs", []):
    print(f"  {c['metric']:15} {c['direction']:10} z={c['magnitude_z']:+.2f}  →  {c['construct']}")

print("\n# Search Queries\n")
print(json.dumps(final_state.get("search_queries", []), indent=2, ensure_ascii=False))

print("\n# Kept PMIDs (top-scored)\n")
print(final_state.get("pmid_list", []))

print("\n# Literature Summary (per-construct)\n")
print(final_state.get("lit_summary", ""))

if final_state.get("symptom_metric_table"):
    print("\n# Symptom-Metric Table\n")
    print(final_state["symptom_metric_table"])

print("\n# Final Report\n")
print(final_state.get("final_report", ""))