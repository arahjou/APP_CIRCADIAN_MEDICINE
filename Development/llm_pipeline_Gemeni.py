# Block I
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time
import difflib
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict

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

import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tools.llm_conversation as _lc
from tools.llm_conversation import _compact_report_for_llm, _parse_structured_queries, _sanitize_pmids
from tools.pubmed_search import RetrievalConfig, evidence_to_text, search_pubmed

print("Imports OK")
print("Project root:", PROJECT_ROOT)
print("Available Ollama models:")
try:
    print(subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout)
except Exception as exc:
    print(f"Could not list Ollama models: {exc}")


# Block II
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

# MODIFIED: Increased retrieval limits to capture more relevant literature
RETRIEVAL_CFG = RetrievalConfig(
    retmax_per_query=25,
    keep_per_query=8,
    max_total_items=25,
    years_back=15,
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


# Block III
con = sqlite3.connect(DB_PATH)
rows = con.execute(
    "SELECT username, period_id_1, period_id_2, audience, model, created_at "
    "FROM ai_analysis_runs ORDER BY created_at DESC"
).fetchall()
print(f"Available rows: {len(rows)}")
for r in rows[:20]:
    print(f"  username={r[0]:<10} P1={r[1]:<10} P2={r[2]:<10} audience={r[3]:<10} model={r[4]:<14} created={r[5]}")

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


# Block IV
AGENT1_SYSTEM = _lc._AGENT1_SYSTEM
AGENT2_SYSTEM = _lc._AGENT2_SYSTEM
AGENT2_ANAMNESIS_ADDENDUM = _lc._AGENT2_ANAMNESIS_ADDENDUM
RELEVANCE_SYSTEM = _lc._RELEVANCE_SYSTEM
AGENT4_SYSTEM = _lc._AGENT4_SYSTEM
AGENT6_SYSTEM = _lc._AGENT6_SYSTEM
AGENT5_AUDIENCES = dict(_lc._AGENT5_AUDIENCES)

print("Prompts loaded from tools.llm_conversation.py")
print("Editable prompt variables:")
print("AGENT1_SYSTEM, AGENT2_SYSTEM, RELEVANCE_SYSTEM, AGENT4_SYSTEM, AGENT6_SYSTEM, AGENT5_AUDIENCES")


# Block V
class PipelineState(TypedDict, total=False):
    compact_report: str
    audience: str
    anamnesis: str
    tuning_memory: str
    data_summary: str
    search_queries: list[dict]
    evidence_items: list[dict]
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
    data = {"notes": []}
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
    trace.append({"node": node, "model": AGENT_CONFIG.get(node, {}).get("model"), "output": output_summary})
    return trace

def chat_node(node: str, system: str, user: str, *, json_mode: bool = False) -> str:
    cfg = AGENT_CONFIG[node]
    model_names = [cfg["model"]]
    if cfg.get("fallback_model") and cfg["fallback_model"] not in model_names:
        model_names.append(cfg["fallback_model"])

    last_error: Exception | None = None
    for model_name in model_names:
        try:
            kwargs: dict[str, Any] = {"model": model_name, "temperature": cfg.get("temperature", 0.2)}
            if json_mode:
                kwargs["format"] = "json"
            llm = ChatOllama(**kwargs)
            response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
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
    for key in ["data_summary", "search_queries", "pmid_list", "lit_summary", "symptom_metric_table", "final_report"]:
        value = state.get(key)
        if isinstance(value, str):
            print(f"{key:22} {len(value):5} chars")
        elif isinstance(value, list):
            print(f"{key:22} {len(value):5} items")
        else:
            print(f"{key:22} {type(value).__name__}")


# Block VI
def data_summariser(state: PipelineState) -> PipelineState:
    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Actigraphy Metrics\n{state['compact_report']}\n\n"
        "Summarise these metrics for a downstream literature researcher."
    )
    summary = chat_node("data_summariser", AGENT1_SYSTEM, user)
    return {**state, "data_summary": summary, "trace": add_trace(state, "data_summariser", f"{len(summary)} chars")}

def pubmed_query_planner(state: PipelineState) -> PipelineState:
    anamnesis = state.get("anamnesis", "").strip()
    
    # MODIFIED: Aggressive rules to prevent exact matching and quotation marks
    search_rules = (
        "CRITICAL INSTRUCTIONS & PUBMED SEARCH RULES:\n"
        "1. TRANSLATE TO CLINICAL CONCEPTS: Translate specific metric changes into broader clinical phenomena. "
        "(e.g., If SRI/Sleep Regularity Index is low, search for 'sleep irregularity' or 'circadian rhythm disruption', NOT 'SRI').\n"
        "2. NO QUOTATION MARKS: NEVER put quotes around your search terms. Quotes break the PubMed search engine.\n"
        "3. KEEP IT SIMPLE: Use 2 to 3 broad keywords per query. Do not use complex AND/OR boolean logic.\n"
        "4. Output JSON lines query intents."
    )

    if anamnesis:
        user = (
            f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
            f"# Clinical Data Summary\n{state['data_summary']}\n"
            + AGENT2_ANAMNESIS_ADDENDUM.format(anamnesis=anamnesis) + "\n\n"
            + search_rules
        )
    else:
        user = (
            f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
            f"# Clinical Data Summary\n{state['data_summary']}\n\n"
            + search_rules
        )
        
    raw = chat_node("pubmed_query_planner", AGENT2_SYSTEM, user)
    queries = _parse_structured_queries(raw)
    
    if not queries:
        queries = [
            {
                "topic": "circadian rhythm actigraphy",
                "population": "humans",
                "context": "sleep regularity",
                "expected_link": "actigraphy rhythm disruption and sleep-wake outcomes",
            },
            {
                "topic": "light exposure circadian",
                "population": "humans",
                "context": "phase alignment",
                "expected_link": "light timing and circadian alignment",
            },
        ]
    return {**state, "search_queries": queries, "trace": add_trace(state, "pubmed_query_planner", f"{len(queries)} queries")}

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

    user = (
        f"Clinical summary:\n{state.get('data_summary', '')}\n\n"
        f"Query intents:\n{json.dumps(state.get('search_queries', []), ensure_ascii=False)}\n\n"
        f"Evidence items:\n{json.dumps(items, ensure_ascii=False)}"
    )
    raw = chat_node("relevance_judge", RELEVANCE_SYSTEM, user, json_mode=True)
    keep_pmids = extract_json_keep_pmids(raw)
    if keep_pmids:
        items = [x for x in items if str(x.get("pmid")) in keep_pmids]
    pmids = [str(x.get("pmid")) for x in items if x.get("pmid")]
    return {
        **state,
        "evidence_items": items,
        "pmid_list": pmids,
        "raw_abstracts": evidence_to_text(items),
        "trace": add_trace(state, "relevance_judge", f"kept {len(items)} items"),
    }

def literature_synthesiser(state: PipelineState) -> PipelineState:
    # MODIFIED: Forcing a synthesized narrative rather than a robotic list
    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# PubMed Abstracts\n{state['raw_abstracts']}\n\n"
        "Synthesize a cohesive 200-word narrative. DO NOT just list papers sequentially. "
        "Instead, directly connect the literature findings to the patient's specific actigraphy changes "
        "(e.g., explain WHY their observed sleep irregularity matters based on the evidence). "
        "Write in flowing, clinical prose."
    )
    summary = chat_node("literature_synthesiser", AGENT4_SYSTEM, user)
    return {**state, "lit_summary": summary, "trace": add_trace(state, "literature_synthesiser", f"{len(summary)} chars")}

def symptom_metric_linker(state: PipelineState) -> PipelineState:
    user = (
        f"# Patient Anamnesis\n{state.get('anamnesis', '')}\n\n"
        f"# Clinical Data Summary\n{state.get('data_summary', '')}\n\n"
        f"# PubMed Abstracts\n{state.get('raw_abstracts', '')}\n\n"
        "Produce the Symptom-Metric Correlation Table as instructed."
    )
    table = chat_node("symptom_metric_linker", AGENT6_SYSTEM, user)
    return {**state, "symptom_metric_table": table, "trace": add_trace(state, "symptom_metric_linker", f"{len(table)} chars")}

def report_writer(state: PipelineState) -> PipelineState:
    audience = state.get("audience", "layperson")
    system_prompt = AGENT5_AUDIENCES.get(audience, AGENT5_AUDIENCES["layperson"])
    evidence_items = state.get("evidence_items", [])
    has_evidence = bool(evidence_items)

    user = (
        f"# Tuning Memory\n{state.get('tuning_memory', '')}\n\n"
        f"# Actigraphy Data Context\n{state['compact_report']}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Supporting Literature Evidence\n{state['lit_summary']}\n\n"
        f"# Evidence Items (use PMIDs from here only)\n{json.dumps(evidence_items, ensure_ascii=False)}\n\n"
    )
    
    if state.get("symptom_metric_table", "").strip():
        user += (
            f"# Symptom-Metric Correlation\n{state['symptom_metric_table']}\n\n"
            "Include a section titled 'Symptom-Metric Correlation'.\n\n"
        )
        
    # MODIFIED: Forced extremely tight output lengths and formatting constraints
    if has_evidence:
        user += (
            "Write the final report now. "
            "CRITICAL CONSTRAINTS: Keep the report extremely concise (maximum 250 words, readable in < 1 minute). "
            "Use bullet points for actionable takeaways. Avoid repetitive introductions. "
            "Every evidence-backed claim must cite a real PMID from Evidence Items. "
            "Never invent PMIDs. If there is no direct evidence, write '(no direct evidence found)'."
        )
    else:
        user += (
            "Write the final report now. No PubMed evidence was retrieved, so do not cite PMIDs. "
            "CRITICAL CONSTRAINTS: Keep the report extremely concise (maximum 250 words, readable in < 1 minute). "
            "Use bullet points for actionable takeaways. Only report data-driven findings and mark unsupported claims as '(no direct evidence found)'."
        )

    report = chat_node("report_writer", system_prompt, user)
    allowed = {str(p) for p in state.get("pmid_list", [])}
    report = _sanitize_pmids(report, allowed)

    claim_map: dict[str, list[str]] = {}
    for line in report.splitlines():
        cited = [p for p in re.findall(r"PMID\s*[:#-]?\s*(\d+)", line) if p in allowed]
        if cited:
            claim_map[line.strip()[:180]] = cited

    if allowed:
        refs = ["\n\n---\nReferences (PubMed):"]
        for i, pmid in enumerate(state.get("pmid_list", []), start=1):
            refs.append(f"{i}. PMID {pmid} - https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        report += "\n".join(refs)

    return {**state, "final_report": report, "claim_to_pmid_map": claim_map, "trace": add_trace(state, "report_writer", f"{len(report)} chars")}

def tuning_memory_writer(state: PipelineState) -> PipelineState:
    note = (
        f"audience={state.get('audience')} | queries={len(state.get('search_queries', []))} | "
        f"kept_pmids={len(state.get('pmid_list', []))} | "
        f"models=" + ", ".join(f"{k}:{v['model']}" for k, v in AGENT_CONFIG.items())
    )
    save_tuning_memory(note)
    return {**state, "trace": add_trace(state, "tuning_memory_writer", "saved tuning note")}

def route_after_synthesis(state: PipelineState) -> str:
    return "symptom_metric_linker" if state.get("anamnesis", "").strip() else "report_writer"


# Block VII
def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("data_summariser", data_summariser)
    graph.add_node("pubmed_query_planner", pubmed_query_planner)
    graph.add_node("pubmed_retriever", pubmed_retriever)
    graph.add_node("relevance_judge", relevance_judge)
    graph.add_node("literature_synthesiser", literature_synthesiser)
    graph.add_node("symptom_metric_linker", symptom_metric_linker)
    graph.add_node("report_writer", report_writer)
    graph.add_node("tuning_memory_writer", tuning_memory_writer)

    graph.set_entry_point("data_summariser")
    graph.add_edge("data_summariser", "pubmed_query_planner")
    graph.add_edge("pubmed_query_planner", "pubmed_retriever")
    graph.add_edge("pubmed_retriever", "relevance_judge")
    graph.add_edge("relevance_judge", "literature_synthesiser")
    graph.add_conditional_edges(
        "literature_synthesiser",
        route_after_synthesis,
        {"symptom_metric_linker": "symptom_metric_linker", "report_writer": "report_writer"},
    )
    graph.add_edge("symptom_metric_linker", "report_writer")
    graph.add_edge("report_writer", "tuning_memory_writer")
    graph.add_edge("tuning_memory_writer", END)

    if MemorySaver is not None:
        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()

AGENT_GRAPH = build_graph()
print("LangGraph compiled")
print("Nodes:", list(AGENT_CONFIG.keys()) + ["pubmed_retriever", "tuning_memory_writer"])
print("Checkpointing:", "MemorySaver" if MemorySaver is not None else "not available")


# Block VIII
initial_state: PipelineState = {
    "compact_report": compact_report,
    "audience": AUDIENCE,
    "anamnesis": ANAMNESIS.strip(),
    "tuning_memory": load_tuning_memory(),
    "data_summary": "",
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


# Block IX
print("# Data Summary\n")
print(final_state.get("data_summary", ""))
print("\n# Search Queries\n")
print(json.dumps(final_state.get("search_queries", []), indent=2, ensure_ascii=False))
print("\n# PMIDs\n")
print(final_state.get("pmid_list", []))


# Block X
print("# Literature Summary\n")
print(final_state.get("lit_summary", ""))

if final_state.get("symptom_metric_table"):
    print("\n# Symptom-Metric Table\n")
    print(final_state["symptom_metric_table"])

print("\n# Final Report\n")
print(final_state.get("final_report", ""))