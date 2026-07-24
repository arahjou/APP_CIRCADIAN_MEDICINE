from __future__ import annotations

import json
import re
import sqlite3
import subprocess
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

# =========================
# Block I: Locate project root and import project tools
# =========================

PROJECT_ROOT = Path.cwd()
for _ in range(6):
    if (PROJECT_ROOT / "tools" / "llm_conversation.py").exists():
        break
    PROJECT_ROOT = PROJECT_ROOT.parent
else:
    raise RuntimeError("Could not locate project root containing tools/llm_conversation.py")

import sys

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


# =========================
# Block II: Main configuration
# =========================

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
        "model": "qwen3.5:4b",
        "temperature": 0.2,
        "role": "literature synthesis agent",
    },
    "symptom_metric_linker": {
        "model": "qwen3.5:4b",
        "temperature": 0.1,
        "role": "symptom-to-metric mapper",
    },
    "report_writer": {
        "model": "qwen3.5:4b",
        "temperature": 0.2,
        "role": "audience-aware report writer",
    },
}

# Increased retrieval depth compared with your original configuration.
# Your previous values were too restrictive for clinically useful synthesis.
RETRIEVAL_CFG = RetrievalConfig(
    retmax_per_query=40,
    keep_per_query=8,
    max_total_items=35,
    years_back=20,
    humans_only=True,
    adults_only=(AUDIENCE == "doctor"),
)

# Persistent notebook memory: stores successful tuning notes across notebook sessions.
USE_TUNING_MEMORY = True
MEMORY_PATH = PROJECT_ROOT / "Development" / "llm_pipeline_tuning_memory.json"

# LangGraph short-term checkpointing. If MemorySaver is available, this lets a run be resumed by thread_id.
THREAD_ID = "llm-pipeline-tuning"

for node, cfg in AGENT_CONFIG.items():
    fallback = f" fallback={cfg['fallback_model']}" if "fallback_model" in cfg else ""
    print(f"{node:24} model={cfg['model']} temp={cfg['temperature']}{fallback}")


# =========================
# Block III: Load latest analysis row from SQLite
# =========================

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


# =========================
# Block IV: Load and modify prompts
# =========================

AGENT1_SYSTEM = _lc._AGENT1_SYSTEM
AGENT2_SYSTEM = _lc._AGENT2_SYSTEM
AGENT2_ANAMNESIS_ADDENDUM = _lc._AGENT2_ANAMNESIS_ADDENDUM
RELEVANCE_SYSTEM = _lc._RELEVANCE_SYSTEM
AGENT4_SYSTEM = _lc._AGENT4_SYSTEM
AGENT6_SYSTEM = _lc._AGENT6_SYSTEM
AGENT5_AUDIENCES = dict(_lc._AGENT5_AUDIENCES)

# Shorter, audience-specific final report prompts.
# This directly addresses the problem that the final summary is too long for doctors/patients.
AGENT5_AUDIENCES["doctor"] = """
You write for a busy medical doctor.

Goal:
Produce a short clinical interpretation, not a full literature review.

Format:
1. Bottom line: one sentence.
2. Key actigraphy changes: maximum 3 bullets.
3. Literature context: maximum 2 bullets.
4. Clinical caution: one sentence.

Rules:
- Maximum 170 words.
- Do not list every metric.
- Prioritize the most clinically meaningful changes.
- Use plain clinical language.
- Cite PMIDs only when directly relevant.
- Do not invent PMIDs.
- Do not include long reference lists.
"""

AGENT5_AUDIENCES["layperson"] = """
You write for a patient.

Goal:
Give a very short, understandable explanation.

Format:
1. Main message: one sentence.
2. What changed: maximum 3 bullets.
3. What it may mean: maximum 2 bullets.
4. What to discuss with clinician: one sentence.

Rules:
- Maximum 140 words.
- Avoid technical abbreviations when possible.
- Do not sound alarming.
- Do not diagnose.
- Do not include long references.
"""

AGENT5_AUDIENCES["expert"] = """
You write for a chronobiology / sleep research expert.

Goal:
Give a concise but technically meaningful interpretation.

Rules:
- Maximum 260 words.
- Mention the most important metrics.
- Integrate actigraphy changes with literature.
- Use PMIDs only when directly relevant.
- Avoid generic textbook explanations.
"""

print("Prompts loaded from tools.llm_conversation.py")
print("Editable prompt variables:")
print("AGENT1_SYSTEM, AGENT2_SYSTEM, RELEVANCE_SYSTEM, AGENT4_SYSTEM, AGENT6_SYSTEM, AGENT5_AUDIENCES")


# =========================
# Block V: State and utility functions
# =========================

class PipelineState(TypedDict, total=False):
    compact_report: str
    audience: str
    anamnesis: str
    tuning_memory: str
    data_summary: str
    change_interpretations: list[dict[str, Any]]
    search_queries: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    raw_abstracts: str
    pmid_list: list[str]
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
    data: dict[str, Any] = {"notes": []}

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
    trace.append(
        {
            "node": node,
            "model": AGENT_CONFIG.get(node, {}).get("model"),
            "output": output_summary,
        }
    )
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
            response = llm.invoke(
                [SystemMessage(content=system), HumanMessage(content=user)]
            )
            content = response.content
            return content.strip() if isinstance(content, str) else str(content).strip()
        except Exception as exc:
            last_error = exc
            print(f"{node}: model {model_name} failed: {exc!r}")

    raise RuntimeError(f"{node} failed for all configured models") from last_error


def extract_json_keep_pmids(raw: str) -> set[str]:
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        parsed = json.loads(match.group(0)) if match else {}

    if isinstance(parsed, dict):
        items = parsed.get("keep_pmids") or parsed.get("pmids") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    return {str(x) for x in items}


def print_state_keys(state: PipelineState) -> None:
    for key in [
        "data_summary",
        "change_interpretations",
        "search_queries",
        "pmid_list",
        "lit_summary",
        "symptom_metric_table",
        "final_report",
    ]:
        value = state.get(key)
        if isinstance(value, str):
            print(f"{key:26} {len(value):5} chars")
        elif isinstance(value, list):
            print(f"{key:26} {len(value):5} items")
        else:
            print(f"{key:26} {type(value).__name__}")


# =========================
# Block VI-A: Deterministic metric-change interpretation
# =========================

DOWN_RE = re.compile(
    r"\b(decreas\w*|declin\w*|drop\w*|lower|reduc\w*|went down|down|worsen\w*)\b|↓",
    re.I,
)

UP_RE = re.compile(
    r"\b(increas\w*|rise\w*|higher|elevat\w*|went up|up|greater|more|improv\w*)\b|↑",
    re.I,
)

DELAY_RE = re.compile(
    r"\b(delay\w*|later|shifted later|phase delay)\b",
    re.I,
)

ADVANCE_RE = re.compile(
    r"\b(advanc\w*|earlier|shifted earlier|phase advance)\b",
    re.I,
)

METRIC_DIRECTION_ONTOLOGY: dict[str, dict[str, Any]] = {
    "SRI": {
        "aliases": ["SRI", "Sleep Regularity Index", "sleep regularity index"],
        "decrease": {
            "concept": "increased sleep-wake irregularity",
            "patient_meaning": "sleep timing became less regular",
            "query_terms": [
                "sleep irregularity",
                "sleep-wake irregularity",
                "sleep timing variability",
                "irregular sleep wake rhythm",
                "sleep regularity",
            ],
            "avoid_primary_terms": ["SRI", "Sleep Regularity Index"],
        },
        "increase": {
            "concept": "improved sleep-wake regularity",
            "patient_meaning": "sleep timing became more regular",
            "query_terms": [
                "sleep regularity",
                "regular sleep timing",
                "sleep-wake regularity",
                "stable sleep schedule",
            ],
            "avoid_primary_terms": ["SRI"],
        },
    },
    "IS": {
        "aliases": ["IS", "Interdaily Stability", "interdaily stability"],
        "decrease": {
            "concept": "weaker day-to-day circadian rhythm stability",
            "patient_meaning": "daily rest-activity timing became less stable",
            "query_terms": [
                "circadian rhythm instability",
                "rest activity rhythm disruption",
                "interdaily stability",
                "sleep wake rhythm disruption",
            ],
            "avoid_primary_terms": ["IS"],
        },
        "increase": {
            "concept": "stronger day-to-day circadian rhythm stability",
            "patient_meaning": "daily rest-activity timing became more stable",
            "query_terms": [
                "circadian rhythm stability",
                "rest activity rhythm stability",
                "stable sleep wake rhythm",
                "interdaily stability",
            ],
            "avoid_primary_terms": ["IS"],
        },
    },
    "IV": {
        "aliases": ["IV", "Intradaily Variability", "intradaily variability"],
        "increase": {
            "concept": "increased rhythm fragmentation",
            "patient_meaning": "rest and activity became more fragmented across the day",
            "query_terms": [
                "rest activity rhythm fragmentation",
                "circadian rhythm fragmentation",
                "sleep wake fragmentation",
                "intradaily variability",
            ],
            "avoid_primary_terms": ["IV"],
        },
        "decrease": {
            "concept": "reduced rhythm fragmentation",
            "patient_meaning": "rest and activity became less fragmented",
            "query_terms": [
                "reduced rhythm fragmentation",
                "rest activity rhythm consolidation",
                "sleep wake consolidation",
                "intradaily variability",
            ],
            "avoid_primary_terms": ["IV"],
        },
    },
    "RA": {
        "aliases": ["RA", "Relative Amplitude", "relative amplitude"],
        "decrease": {
            "concept": "blunted rest-activity rhythm amplitude",
            "patient_meaning": "the contrast between active daytime and quiet nighttime became weaker",
            "query_terms": [
                "blunted rest activity rhythm",
                "low relative amplitude",
                "reduced circadian amplitude",
                "rest activity rhythm amplitude",
            ],
            "avoid_primary_terms": ["RA"],
        },
        "increase": {
            "concept": "stronger rest-activity rhythm amplitude",
            "patient_meaning": "the day-night activity contrast became stronger",
            "query_terms": [
                "rest activity rhythm amplitude",
                "circadian amplitude",
                "relative amplitude actigraphy",
                "day night activity contrast",
            ],
            "avoid_primary_terms": ["RA"],
        },
    },
    "L5": {
        "aliases": ["L5", "least active 5 hours", "least active five hours"],
        "increase": {
            "concept": "increased nocturnal/rest-period activity",
            "patient_meaning": "activity during the quietest/rest period increased",
            "query_terms": [
                "nocturnal activity",
                "sleep disruption",
                "rest period activity",
                "nighttime activity actigraphy",
            ],
            "avoid_primary_terms": ["L5"],
        },
        "decrease": {
            "concept": "lower nocturnal/rest-period activity",
            "patient_meaning": "activity during the quietest/rest period decreased",
            "query_terms": [
                "sleep consolidation",
                "reduced nocturnal activity",
                "rest period activity",
                "nighttime activity actigraphy",
            ],
            "avoid_primary_terms": ["L5"],
        },
    },
    "M10": {
        "aliases": ["M10", "most active 10 hours", "most active ten hours"],
        "decrease": {
            "concept": "reduced daytime activity level",
            "patient_meaning": "activity during the most active part of the day decreased",
            "query_terms": [
                "reduced daytime activity",
                "low physical activity",
                "rest activity rhythm amplitude",
                "daytime activity actigraphy",
            ],
            "avoid_primary_terms": ["M10"],
        },
        "increase": {
            "concept": "increased daytime activity level",
            "patient_meaning": "activity during the most active part of the day increased",
            "query_terms": [
                "daytime physical activity",
                "increased daytime activity",
                "physical activity actigraphy",
                "rest activity rhythm",
            ],
            "avoid_primary_terms": ["M10"],
        },
    },
    "CPD": {
        "aliases": ["CPD", "Composite Phase Deviation", "composite phase deviation"],
        "increase": {
            "concept": "increased circadian misalignment",
            "patient_meaning": "behavioral timing became more misaligned",
            "query_terms": [
                "circadian misalignment",
                "sleep timing misalignment",
                "social jetlag",
                "circadian disruption",
            ],
            "avoid_primary_terms": ["CPD"],
        },
        "decrease": {
            "concept": "reduced circadian misalignment",
            "patient_meaning": "behavioral timing became better aligned",
            "query_terms": [
                "circadian alignment",
                "reduced circadian misalignment",
                "sleep timing alignment",
                "social jetlag",
            ],
            "avoid_primary_terms": ["CPD"],
        },
    },
    "acrophase": {
        "aliases": ["acrophase", "activity acrophase", "cosinor acrophase"],
        "increase": {
            "concept": "delayed activity rhythm phase",
            "patient_meaning": "the peak activity timing shifted later",
            "query_terms": [
                "delayed sleep phase",
                "circadian phase delay",
                "delayed activity rhythm",
                "late chronotype",
            ],
            "avoid_primary_terms": ["acrophase"],
        },
        "decrease": {
            "concept": "advanced activity rhythm phase",
            "patient_meaning": "the peak activity timing shifted earlier",
            "query_terms": [
                "advanced sleep phase",
                "circadian phase advance",
                "advanced activity rhythm",
                "chronotype",
            ],
            "avoid_primary_terms": ["acrophase"],
        },
        "delay": {
            "concept": "delayed activity rhythm phase",
            "patient_meaning": "the peak activity timing shifted later",
            "query_terms": [
                "delayed sleep phase",
                "circadian phase delay",
                "delayed activity rhythm",
                "late chronotype",
            ],
            "avoid_primary_terms": ["acrophase"],
        },
        "advance": {
            "concept": "advanced activity rhythm phase",
            "patient_meaning": "the peak activity timing shifted earlier",
            "query_terms": [
                "advanced sleep phase",
                "circadian phase advance",
                "advanced activity rhythm",
                "chronotype",
            ],
            "avoid_primary_terms": ["acrophase"],
        },
    },
    "sleep_efficiency": {
        "aliases": ["sleep efficiency", "Sleep Efficiency", "SE"],
        "decrease": {
            "concept": "reduced sleep continuity",
            "patient_meaning": "sleep became less efficient or more interrupted",
            "query_terms": [
                "poor sleep efficiency",
                "sleep continuity",
                "sleep fragmentation",
                "actigraphy sleep efficiency",
            ],
            "avoid_primary_terms": ["SE"],
        },
        "increase": {
            "concept": "improved sleep continuity",
            "patient_meaning": "sleep became more efficient or less interrupted",
            "query_terms": [
                "sleep efficiency",
                "sleep continuity",
                "sleep consolidation",
                "actigraphy sleep efficiency",
            ],
            "avoid_primary_terms": ["SE"],
        },
    },
    "WASO": {
        "aliases": ["WASO", "wake after sleep onset"],
        "increase": {
            "concept": "increased sleep fragmentation",
            "patient_meaning": "wakefulness during the sleep period increased",
            "query_terms": [
                "wake after sleep onset",
                "sleep fragmentation",
                "sleep continuity",
                "nighttime awakenings",
            ],
            "avoid_primary_terms": [],
        },
        "decrease": {
            "concept": "reduced sleep fragmentation",
            "patient_meaning": "wakefulness during the sleep period decreased",
            "query_terms": [
                "reduced wake after sleep onset",
                "sleep consolidation",
                "sleep continuity",
                "nighttime awakenings",
            ],
            "avoid_primary_terms": [],
        },
    },
}


def alias_appears(text: str, alias: str) -> bool:
    """
    Safer alias matching.

    Important: abbreviations such as IS, IV, RA, and SE should not be searched
    case-insensitively, otherwise 'IS' can match the normal word 'is'.
    """
    alias = alias.strip()
    if not alias:
        return False

    # Short all-uppercase abbreviations: exact case only.
    if len(alias) <= 3 and alias.isupper():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text) is not None

    # Mixed or long labels: case-insensitive phrase matching.
    return re.search(rf"\b{re.escape(alias)}\b", text, flags=re.I) is not None


def infer_direction_from_text(text: str, metric: str | None = None) -> str | None:
    """
    Infer direction from surrounding text.
    For acrophase, later/earlier are more meaningful than increase/decrease.
    """
    if metric == "acrophase":
        if DELAY_RE.search(text):
            return "delay"
        if ADVANCE_RE.search(text):
            return "advance"

    has_down = bool(DOWN_RE.search(text))
    has_up = bool(UP_RE.search(text))

    if has_down and not has_up:
        return "decrease"
    if has_up and not has_down:
        return "increase"

    return None


def interpret_metric_changes(text: str) -> list[dict[str, Any]]:
    """
    Converts metric-level changes into broader clinical/literature concepts.

    This prevents PubMed searches from becoming too abbreviation-driven.
    Example:
    SRI decreased -> increased sleep-wake irregularity -> search sleep irregularity.
    """
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    interpretations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for metric, cfg in METRIC_DIRECTION_ONTOLOGY.items():
        aliases = cfg.get("aliases", [])

        for i, line in enumerate(lines):
            if not any(alias_appears(line, alias) for alias in aliases):
                continue

            window = " ".join(lines[max(0, i - 1): min(len(lines), i + 2)])
            direction = infer_direction_from_text(window, metric=metric)

            if not direction:
                continue

            key = (metric, direction)
            if key in seen:
                continue

            concept_cfg = cfg.get(direction)
            if not concept_cfg:
                continue

            interpretations.append(
                {
                    "metric": metric,
                    "detected_direction": direction,
                    "source_text": window[:500],
                    "concept": concept_cfg["concept"],
                    "patient_meaning": concept_cfg["patient_meaning"],
                    "query_terms": concept_cfg["query_terms"],
                    "avoid_primary_terms": concept_cfg.get("avoid_primary_terms", []),
                }
            )
            seen.add(key)

    return interpretations


# =========================
# Block VI-B: Query construction helpers
# =========================

QUERY_PLANNER_ADDENDUM = """
You are planning PubMed searches.

Important rule:
Do not search primarily for actigraphy metric abbreviations such as SRI, IS, IV, RA, L5, M10, or CPD.

Instead, search for the broader clinical or physiological meaning of the detected change.

Examples:
- SRI decreased -> search for sleep irregularity, sleep-wake irregularity, sleep timing variability.
- IV increased -> search for rest-activity rhythm fragmentation or sleep-wake fragmentation.
- RA decreased -> search for blunted rest-activity rhythm amplitude or reduced circadian amplitude.
- L5 increased -> search for nocturnal activity, sleep disruption, rest-period activity.
- M10 decreased -> search for reduced daytime activity or low physical activity.
- CPD increased -> search for circadian misalignment, social jetlag, sleep timing misalignment.
- Acrophase delayed -> search for circadian phase delay, delayed sleep phase, late chronotype.

Output JSON lines or a JSON list.
Each item must contain:
{
  "topic": "... broad biomedical concept ...",
  "population": "humans",
  "context": "... actigraphy / sleep / circadian context ...",
  "expected_link": "... how this evidence helps interpret the detected change ..."
}

Keep queries general enough to retrieve literature, but specific enough to be clinically relevant.
"""


def build_base_queries_from_interpretations(
    interpretations: list[dict[str, Any]],
    max_queries: int = 8,
) -> list[dict[str, str]]:
    queries: list[dict[str, str]] = []

    for item in interpretations:
        query_terms = item.get("query_terms", [])
        if not query_terms:
            continue

        primary = str(query_terms[0])
        secondary = ", ".join(str(x) for x in query_terms[1:4])

        queries.append(
            {
                "topic": primary,
                "population": "humans",
                "context": f"actigraphy, sleep-wake rhythm, circadian rhythm; related terms: {secondary}",
                "expected_link": (
                    f"Detected change: {item.get('metric')} {item.get('detected_direction')}. "
                    f"Interpretation: {item.get('concept')}. "
                    f"Use literature to explain whether this pattern is clinically relevant."
                ),
            }
        )

    return queries[:max_queries]


def deduplicate_queries(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for q in queries:
        topic = str(q.get("topic", "")).lower().strip()
        context = str(q.get("context", "")).lower().strip()
        key = (topic, context[:80])

        if not topic or key in seen:
            continue

        seen.add(key)
        out.append(q)

    return out


def merge_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    merged = []

    for item in items:
        pmid = str(item.get("pmid", "")).strip()
        if not pmid or pmid in seen:
            continue
        seen.add(pmid)
        merged.append(item)

    return merged


def build_fallback_queries_from_interpretations(
    interpretations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    fallback: list[dict[str, str]] = []

    for item in interpretations:
        concept = item.get("concept", "")
        query_terms = item.get("query_terms", [])

        for term in query_terms[:3]:
            fallback.append(
                {
                    "topic": str(term),
                    "population": "humans",
                    "context": "sleep, circadian rhythm, actigraphy, clinical outcomes",
                    "expected_link": f"broader evidence for {concept}",
                }
            )

    fallback.extend(
        [
            {
                "topic": "sleep-wake rhythm disruption",
                "population": "humans",
                "context": "actigraphy and clinical outcomes",
                "expected_link": "general clinical relevance of disrupted sleep-wake rhythm",
            },
            {
                "topic": "rest-activity rhythm disruption",
                "population": "humans",
                "context": "actigraphy and circadian rhythm",
                "expected_link": "general clinical relevance of disrupted rest-activity rhythms",
            },
            {
                "topic": "sleep timing variability",
                "population": "humans",
                "context": "sleep regularity, actigraphy, clinical outcomes",
                "expected_link": "general clinical relevance of variable sleep timing",
            },
        ]
    )

    return deduplicate_queries(fallback)


# =========================
# Block VI-C: Report compression helpers
# =========================

REPORT_WORD_LIMITS = {
    "doctor": 170,
    "layperson": 140,
    "expert": 260,
}


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def compress_report_if_needed(
    report: str,
    state: PipelineState,
    system_prompt: str,
) -> str:
    audience = state.get("audience", "layperson")
    max_words = REPORT_WORD_LIMITS.get(audience, 160)

    if count_words(report) <= max_words:
        return report

    user = (
        f"Condense the following report to maximum {max_words} words.\n"
        "Preserve the main clinical interpretation and real PMID citations if present.\n"
        "Remove repetition, generic explanations, and long references.\n\n"
        f"# Report to condense\n{report}"
    )

    shortened = chat_node("report_writer", system_prompt, user)
    return shortened.strip()


# =========================
# Block VII: LangGraph node functions
# =========================

def data_summariser(state: PipelineState) -> PipelineState:
    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Actigraphy Metrics\n{state['compact_report']}\n\n"
        "Summarise these metrics for a downstream literature researcher. "
        "Explicitly mention direction of clinically relevant changes using words like increased, decreased, delayed, advanced, worsened, or improved."
    )
    summary = chat_node("data_summariser", AGENT1_SYSTEM, user)
    return {
        **state,
        "data_summary": summary,
        "trace": add_trace(state, "data_summariser", f"{len(summary)} chars"),
    }


def deterministic_change_interpreter(state: PipelineState) -> PipelineState:
    text = state.get("compact_report", "") + "\n\n" + state.get("data_summary", "")
    interpretations = interpret_metric_changes(text)

    return {
        **state,
        "change_interpretations": interpretations,
        "trace": add_trace(
            state,
            "deterministic_change_interpreter",
            f"{len(interpretations)} interpreted metric changes",
        ),
    }


def pubmed_query_planner(state: PipelineState) -> PipelineState:
    anamnesis = state.get("anamnesis", "").strip()
    interpretations = state.get("change_interpretations", [])
    base_queries = build_base_queries_from_interpretations(interpretations)

    if anamnesis:
        user = (
            f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
            f"# Clinical Data Summary\n{state['data_summary']}\n\n"
            f"# Deterministic Metric Interpretations\n"
            f"{json.dumps(interpretations, indent=2, ensure_ascii=False)}\n\n"
            f"# Base Queries Already Suggested\n"
            f"{json.dumps(base_queries, indent=2, ensure_ascii=False)}\n\n"
            + AGENT2_ANAMNESIS_ADDENDUM.format(anamnesis=anamnesis)
            + "\n\n"
            + QUERY_PLANNER_ADDENDUM
        )
    else:
        user = (
            f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
            f"# Clinical Data Summary\n{state['data_summary']}\n\n"
            f"# Deterministic Metric Interpretations\n"
            f"{json.dumps(interpretations, indent=2, ensure_ascii=False)}\n\n"
            f"# Base Queries Already Suggested\n"
            f"{json.dumps(base_queries, indent=2, ensure_ascii=False)}\n\n"
            + QUERY_PLANNER_ADDENDUM
        )

    raw = chat_node("pubmed_query_planner", AGENT2_SYSTEM, user)
    llm_queries = _parse_structured_queries(raw)
    queries = deduplicate_queries(base_queries + llm_queries)

    if not queries:
        queries = [
            {
                "topic": "sleep irregularity",
                "population": "humans",
                "context": "actigraphy, sleep timing variability, sleep-wake rhythm",
                "expected_link": "general interpretation of irregular sleep-wake patterns",
            },
            {
                "topic": "circadian rhythm disruption",
                "population": "humans",
                "context": "actigraphy, rest-activity rhythm, clinical outcomes",
                "expected_link": "general interpretation of disrupted rest-activity rhythms",
            },
        ]

    return {
        **state,
        "search_queries": queries,
        "trace": add_trace(state, "pubmed_query_planner", f"{len(queries)} queries"),
    }


def pubmed_retriever(state: PipelineState) -> PipelineState:
    queries = state.get("search_queries", [])
    items = search_pubmed(queries, config=RETRIEVAL_CFG)

    MIN_EVIDENCE_ITEMS = 10

    if len(items) < MIN_EVIDENCE_ITEMS:
        fallback_queries = build_fallback_queries_from_interpretations(
            state.get("change_interpretations", [])
        )
        fallback_items = search_pubmed(fallback_queries, config=RETRIEVAL_CFG)
        items = merge_evidence_items(items + fallback_items)

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
        return {
            **state,
            "trace": add_trace(state, "relevance_judge", "skipped; no evidence"),
        }

    user = (
        f"Clinical summary:\n{state.get('data_summary', '')}\n\n"
        f"Deterministic metric interpretations:\n"
        f"{json.dumps(state.get('change_interpretations', []), ensure_ascii=False)}\n\n"
        f"Query intents:\n{json.dumps(state.get('search_queries', []), ensure_ascii=False)}\n\n"
        f"Evidence items:\n{json.dumps(items, ensure_ascii=False)}"
    )

    raw = chat_node("relevance_judge", RELEVANCE_SYSTEM, user, json_mode=True)
    keep_pmids = extract_json_keep_pmids(raw)

    # Avoid over-filtering. A small local LLM judge can be too strict.
    MIN_ITEMS_AFTER_JUDGE = 8

    if keep_pmids and len(keep_pmids) >= MIN_ITEMS_AFTER_JUDGE:
        items = [x for x in items if str(x.get("pmid")) in keep_pmids]
    else:
        items = items[: max(MIN_ITEMS_AFTER_JUDGE, min(len(items), 18))]

    pmids = [str(x.get("pmid")) for x in items if x.get("pmid")]

    return {
        **state,
        "evidence_items": items,
        "pmid_list": pmids,
        "raw_abstracts": evidence_to_text(items),
        "trace": add_trace(state, "relevance_judge", f"kept {len(items)} items"),
    }


INTEGRATED_SYNTHESIS_ADDENDUM = """
You are not writing a generic literature review.

Your task is to integrate:
1. The deterministic actigraphy changes.
2. Their broader clinical meaning.
3. The PubMed evidence.

Write in a clinically natural way.

Avoid this robotic structure:
"Study A found X. Study B found Y."

Prefer:
"The observed reduction in sleep regularity is best interpreted as increased sleep-wake irregularity. This matters because studies of irregular sleep timing and disrupted rest-activity rhythms link such patterns with poorer sleep continuity, circadian disruption, and worse clinical functioning..."

Rules:
- Do not overclaim causality.
- Do not say the literature proves this patient's condition.
- Use PMIDs only when evidence directly supports the interpretation.
- Focus on the most clinically important 2-4 changes.
- Maximum 220 words.
"""


def literature_synthesiser(state: PipelineState) -> PipelineState:
    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Deterministic Metric Interpretations\n"
        f"{json.dumps(state.get('change_interpretations', []), indent=2, ensure_ascii=False)}\n\n"
        f"# PubMed Abstracts\n{state['raw_abstracts']}\n\n"
        + INTEGRATED_SYNTHESIS_ADDENDUM
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
        f"# Deterministic Metric Interpretations\n"
        f"{json.dumps(state.get('change_interpretations', []), indent=2, ensure_ascii=False)}\n\n"
        f"# PubMed Abstracts\n{state.get('raw_abstracts', '')}\n\n"
        "Produce the Symptom-Metric Correlation Table as instructed. "
        "Prefer broader clinical concepts over metric abbreviations."
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

    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Actigraphy Data Context\n{state['compact_report']}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Deterministic Metric Interpretations\n"
        f"{json.dumps(state.get('change_interpretations', []), indent=2, ensure_ascii=False)}\n\n"
        f"# Supporting Literature Evidence\n{state['lit_summary']}\n\n"
        f"# Evidence Items, use PMIDs from here only\n"
        f"{json.dumps(evidence_items, ensure_ascii=False)}\n\n"
    )

    if state.get("symptom_metric_table", "").strip():
        user += (
            f"# Symptom-Metric Correlation\n{state['symptom_metric_table']}\n\n"
            "Include a short section titled 'Symptom-Metric Correlation'.\n\n"
        )

    if has_evidence:
        user += (
            "Write the final report now. Every evidence-backed claim must cite a real PMID from Evidence Items. "
            "Never invent PMIDs. If there is no direct evidence, write '(no direct evidence found)'. "
            "Keep the report short and clinically integrated."
        )
    else:
        user += (
            "Write the final report now. No PubMed evidence was retrieved, so do not cite PMIDs. "
            "Only report data-driven findings and mark unsupported literature claims as '(no direct evidence found)'. "
            "Keep the report short and clinically integrated."
        )

    report = chat_node("report_writer", system_prompt, user)

    allowed = {str(p) for p in state.get("pmid_list", [])}
    report = _sanitize_pmids(report, allowed)

    claim_map: dict[str, list[str]] = {}
    for line in report.splitlines():
        cited = [p for p in re.findall(r"PMID\s*[:#-]?\s*(\d+)", line) if p in allowed]
        if cited:
            claim_map[line.strip()[:180]] = cited

    # Keep final doctor/patient reports short.
    # Only expert reports receive a compact reference list.
    if allowed and audience == "expert":
        refs = ["\n\n---\nReferences (PubMed):"]
        for i, pmid in enumerate(state.get("pmid_list", [])[:10], start=1):
            refs.append(f"{i}. PMID {pmid} - https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        report += "\n".join(refs)

    report = compress_report_if_needed(report, state, system_prompt)
    report = _sanitize_pmids(report, allowed)

    return {
        **state,
        "final_report": report,
        "claim_to_pmid_map": claim_map,
        "trace": add_trace(state, "report_writer", f"{len(report)} chars"),
    }


def tuning_memory_writer(state: PipelineState) -> PipelineState:
    note = (
        f"audience={state.get('audience')} | "
        f"interpreted_changes={len(state.get('change_interpretations', []))} | "
        f"queries={len(state.get('search_queries', []))} | "
        f"kept_pmids={len(state.get('pmid_list', []))} | "
        f"models=" + ", ".join(f"{k}:{v['model']}" for k, v in AGENT_CONFIG.items())
    )
    save_tuning_memory(note)
    return {
        **state,
        "trace": add_trace(state, "tuning_memory_writer", "saved tuning note"),
    }


def route_after_synthesis(state: PipelineState) -> str:
    return "symptom_metric_linker" if state.get("anamnesis", "").strip() else "report_writer"


# =========================
# Block VIII: Build graph
# =========================

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("data_summariser", data_summariser)
    graph.add_node("deterministic_change_interpreter", deterministic_change_interpreter)
    graph.add_node("pubmed_query_planner", pubmed_query_planner)
    graph.add_node("pubmed_retriever", pubmed_retriever)
    graph.add_node("relevance_judge", relevance_judge)
    graph.add_node("literature_synthesiser", literature_synthesiser)
    graph.add_node("symptom_metric_linker", symptom_metric_linker)
    graph.add_node("report_writer", report_writer)
    graph.add_node("tuning_memory_writer", tuning_memory_writer)

    graph.set_entry_point("data_summariser")
    graph.add_edge("data_summariser", "deterministic_change_interpreter")
    graph.add_edge("deterministic_change_interpreter", "pubmed_query_planner")
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
print(
    "Nodes:",
    [
        "data_summariser",
        "deterministic_change_interpreter",
        "pubmed_query_planner",
        "pubmed_retriever",
        "relevance_judge",
        "literature_synthesiser",
        "symptom_metric_linker",
        "report_writer",
        "tuning_memory_writer",
    ],
)
print("Checkpointing:", "MemorySaver" if MemorySaver is not None else "not available")


# =========================
# Block IX: Run graph
# =========================

initial_state: PipelineState = {
    "compact_report": compact_report,
    "audience": AUDIENCE,
    "anamnesis": ANAMNESIS.strip(),
    "tuning_memory": load_tuning_memory(),
    "data_summary": "",
    "change_interpretations": [],
    "search_queries": [],
    "evidence_items": [],
    "raw_abstracts": "",
    "pmid_list": [],
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
    # Compatibility for older LangGraph versions without this config shape.
    final_state = AGENT_GRAPH.invoke(initial_state)

print(f"Graph finished in {time.time() - t0:.1f}s")
print_state_keys(final_state)

print("\nTrace:")
for step in final_state.get("trace", []):
    print(f"- {step['node']}: {step['output']} [{step.get('model')}]")


# =========================
# Block X: Inspect outputs
# =========================

print("# Data Summary\n")
print(final_state.get("data_summary", ""))

print("\n# Deterministic Change Interpretations\n")
print(json.dumps(final_state.get("change_interpretations", []), indent=2, ensure_ascii=False))

print("\n# Search Queries\n")
print(json.dumps(final_state.get("search_queries", []), indent=2, ensure_ascii=False))

print("\n# PMIDs\n")
print(final_state.get("pmid_list", []))

print("\n# Literature Summary\n")
print(final_state.get("lit_summary", ""))

if final_state.get("symptom_metric_table"):
    print("\n# Symptom-Metric Table\n")
    print(final_state["symptom_metric_table"])

print("\n# Final Report\n")
print(final_state.get("final_report", ""))
