"""
5-Agent LangGraph pipeline for circadian medicine report analysis.

Pipeline:
  JSON Report
      ↓
  [Agent 1: Data Summariser]        ← local Ollama
      → clinical metric summary (~400 words)
      ↓
  [Agent 2: Keyword Extractor]      ← local Ollama (fast model)
      → 3-5 MeSH-style PubMed queries
      ↓
  [Agent 3: Literature Search]      ← PubMed E-utilities API (no patient data sent)
      → raw abstracts (capped at ~8 000 chars)
      ↓
  [Agent 4: Literature Synthesiser] ← local Ollama
      → concise evidence summary (~200 words)
      ↓
  [Agent 5: Report Writer]          ← local Ollama, audience-aware
      → final structured report

Privacy guarantee: only keyword queries reach the internet — raw metrics and
patient identifiers never leave the local machine.
"""

from __future__ import annotations

import json
import os
import re
from typing import TypedDict, Callable

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from tools.pubmed_search import search_pubmed, evidence_to_text, RetrievalConfig
from tools.app_logging import log_event


# ---------------------------------------------------------------------------
# Shared pipeline state
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    """State object passed between all agents."""
    json_filepath: str
    compact_report: str           # Agent 1 input (flattened metrics)
    data_summary: str             # Agent 1 output
    search_queries: list[dict]    # Agent 2 output
    raw_abstracts: str            # Agent 3 output
    pmid_list: list[str]          # Agent 3 output — PubMed IDs of retrieved articles
    evidence_items: list[dict]    # Agent 3 output - structured evidence records
    lit_summary: str              # Agent 4 output
    anamnesis: str                # Doctor/Expert input — patient history & symptoms
    symptom_metric_table: str     # Agent 6 output — symptom → metric → literature map
    claim_to_pmid_map: dict[str, list[str]]  # Agent 5 grounding map
    audience: str                 # "expert" | "doctor" | "layperson"
    final_report: str             # Agent 5 output
    model: str                    # Ollama model name for main agents
    progress_callback: Callable[[str], None] | None  # optional Streamlit status hook


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _compact_report_for_llm(report_data) -> str:
    """Flatten report metrics into a compact, readable text block for LLM context."""
    metadata = report_data.get("metadata", {}) if isinstance(report_data, dict) else {}
    period_ids = metadata.get("period_ids", "Unknown")

    lines = [f"Period IDs: {period_ids}"]

    sections = report_data.get("sections", {}) if isinstance(report_data, dict) else {}
    if not isinstance(sections, dict) or not sections:
        lines.append("Metrics: Unknown")
        return "\n".join(lines)

    for section_name in sorted(sections.keys()):
        section = sections.get(section_name, {})
        if not isinstance(section, dict):
            continue

        for subgroup_name in sorted(section.keys()):
            items = section.get(subgroup_name, [])
            if not isinstance(items, list):
                continue

            for metric in items:
                if not isinstance(metric, dict):
                    continue
                name = metric.get("Name", "Unknown")
                p1 = metric.get("Period1", "Unknown")
                p2 = metric.get("Period2", "Unknown")
                diff = metric.get("Difference", "Unknown")
                lines.append(f"{section_name} | {subgroup_name} | {name}: P1={p1}, P2={p2}, Δ={diff}")

    return "\n".join(lines)


def _notify(state: PipelineState, msg: str) -> None:
    cb = state.get("progress_callback")
    if cb:
        cb(msg)


# ---------------------------------------------------------------------------
# Query validation helpers (Task 1)
# ---------------------------------------------------------------------------

def _parse_structured_queries(raw_text: str) -> list[dict]:
    """
    Agent 2 now returns one JSON object per line:
    {"topic":"...", "population":"...", "context":"...", "expected_link":"..."}
    """
    queries: list[dict] = []
    for line in raw_text.splitlines():
        cleaned = line.strip().strip("`")
        if not cleaned:
            continue
        try:
            obj = json.loads(cleaned)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        topic = str(obj.get("topic") or "").strip()
        context = str(obj.get("context") or "").strip()
        population = str(obj.get("population") or "humans").strip()
        expected_link = str(obj.get("expected_link") or "").strip()
        if len(topic.split()) < 2 or len(context.split()) < 1:
            continue
        queries.append(
            {
                "topic": topic,
                "population": population,
                "context": context,
                "expected_link": expected_link,
            }
        )
        if len(queries) >= 5:
            break
    return queries


# ---------------------------------------------------------------------------
# Abstract relevance filter (Task 2)
# ---------------------------------------------------------------------------

_RELEVANCE_SYSTEM = """You are a biomedical relevance filter.
Input:
1) structured PubMed evidence items (PMID + title + abstract + lexical score)
2) the clinical summary and query intents

Output a single JSON object with this exact shape:
  {"keep_pmids": ["12345678", "23456789", ...]}

Rules:
- keep_pmids must contain ONLY PMIDs from the input evidence items, as strings.
- Keep evidence directly relevant to circadian rhythm, sleep regularity, actigraphy,
  light exposure, chronobiology, or sleep-wake patterns.
- Prefer higher-quality clinical relevance over broad background biology.
- Drop papers that are off-topic for the queries (e.g. ultra-endurance athletes,
  professional tennis players, tangential physiology) UNLESS the clinical summary
  specifically calls them out.
- If none are relevant, return {"keep_pmids": []}.
- Output JSON only, no prose, no markdown."""


def _llm_keep_pmids(
    *,
    evidence_items: list[dict],
    queries: list[dict],
    summary: str,
    fast_model: str,
    fallback_model: str | None = None,
) -> set[str]:
    if not evidence_items:
        return set()
    user_content = (
        f"Clinical summary:\n{summary}\n\n"
        f"Query intents:\n{json.dumps(queries, ensure_ascii=False)}\n\n"
        f"Evidence items:\n{json.dumps(evidence_items, ensure_ascii=False)}"
    )

    models_to_try = [fast_model]
    if fallback_model and fallback_model != fast_model:
        models_to_try.append(fallback_model)

    for model_name in models_to_try:
        try:
            raw = _chat(
                model_name=model_name,
                system=_RELEVANCE_SYSTEM,
                user=user_content,
                temperature=0.0,
                format="json",
            )
            parsed = json.loads(raw)
            # Accept either {"keep_pmids": [...]} or a bare list.
            if isinstance(parsed, dict):
                items = parsed.get("keep_pmids") or parsed.get("pmids") or []
            elif isinstance(parsed, list):
                items = parsed
            else:
                items = []
            if isinstance(items, list) and items:
                return {str(x) for x in items}
        except Exception:
            continue
    return set()


def _chat(
    model_name: str,
    system: str,
    user: str,
    temperature: float = 0.2,
    format: str | None = None,
) -> str:
    kwargs: dict = {"model": model_name, "temperature": temperature}
    if format:
        kwargs["format"] = format
    llm = ChatOllama(**kwargs)
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = response.content
    if isinstance(content, str):
        return content.strip()
    return str(content)


# ---------------------------------------------------------------------------
# Agent system prompts
# ---------------------------------------------------------------------------

_AGENT1_SYSTEM = """You are a circadian medicine data analyst.
Your job is to produce a concise clinical summary of the provided actigraphy metrics for a
downstream literature researcher who needs to find relevant evidence.

Rules:
- Use clinical language (IS, IV, RA, CPD, cosinor amplitude/acrophase, WASO, SRI, etc.).
- Highlight abnormal values, notable trends, and comparisons between Period 1 and Period 2.
- Be specific with numbers and include units where available.
- Do NOT interpret for a lay audience — this is for the literature search step.
- Limit your response to approximately 400 words."""

_AGENT2_SYSTEM = """You are a biomedical literature search specialist.
Given a clinical summary of actigraphy data, extract PubMed query intents.

Rules:
- Output EXACTLY one compact JSON object per line with keys:
  {"topic":"...", "population":"...", "context":"...", "expected_link":"..."}
- Use MeSH-friendly terms in topic/context.
- Focus on the most abnormal or clinically notable findings from the summary.
- Each object should target a distinct aspect.
- topic should be 2–7 words, context 1–6 words, population typically humans/adults.
- Output ONLY JSON lines, no markdown, no commentary."""

_AGENT2_ANAMNESIS_ADDENDUM = """
Additional context — Patient anamnesis (reported symptoms/history):
{anamnesis}

Because an anamnesis is available, generate a MIXED query set:
- 3 query objects focused on the most abnormal circadian/sleep metrics
- 2 additional query objects that combine a symptom with a metric change
Total: exactly 5 JSON lines."""

_AGENT6_SYSTEM = """You are a clinical evidence mapper for a circadian medicine report.
You will receive:
1. A patient anamnesis (reported symptoms and medical history)
2. A clinical summary of actigraphy metric changes between two periods
3. PubMed abstracts retrieved for this patient

Your task: for EACH symptom or complaint reported in the anamnesis, produce ONE row in a
structured table that maps:
  Symptom → Most relevant metric change (Δ) → Literature support (PMID if available)

Output format — use EXACTLY this layout, no extra commentary:

Symptom-Metric Correlation Table
|Symptom|Relevant Metric Change|Evidence Support|PMID|
|---|---|---|---|
|<symptom>|<metric: direction + value>|<1-sentence finding from abstract, or "No direct evidence found">|<PMID or —>|

After the table, add a short section:
"Unexplained symptoms (no supporting literature found):"
- List any symptom where no abstract contained relevant evidence.
- If all symptoms are supported, write: All reported symptoms have supporting literature.

Rules:
- If a symptom is not clearly linked to any metric change, say so explicitly.
- Do NOT diagnose. Use cautious language.
- Be concise."""

_AGENT4_SYSTEM = """You are a scientific summariser for a medical evidence review.
You will receive a set of PubMed abstracts and a clinical data summary.

Your task:
- Identify findings in the abstracts that are relevant to the patient's circadian patterns.
- Extract: key associations, risk factors, and recommendations that are evidence-supported.
- Explicitly link each finding back to specific abnormal metrics mentioned in the data summary.
- Be concise: 200 words maximum.
- Use neutral scientific language. Do not over-interpret."""

_AGENT5_AUDIENCES = {
    "expert": """You are a circadian medicine expert writing a technical report for a peer specialist.

Use technical language: IS, IV, RA, CPD, cosinor amplitude/acrophase/mesor, WASO, SRI, PSG,
DLMO, zeitgeber, phase angle, interdaily stability, relative amplitude, melanopic EDI, etc.
Include specific metric values and Δ changes.
Reference the relevant literature findings where applicable.

Required output structure (use these exact headings):

Summary: <2–3 sentences: key findings and overall circadian phenotype>

1) Circadian Rhythm Parameters:
- <IS, IV, RA values with interpretations>

2) Sleep Architecture Indicators:
- <onset, offset, mid-sleep, WASO, SRI findings>

3) Light Exposure Analysis:
- <daytime/nocturnal melanopic EDI, phase alignment implications>

4) Phase & Cosinor Analysis:
- <acrophase, amplitude, mesor, CPD values and clinical relevance>

5) Literature-Supported Associations:
- <evidence-based links to risk factors or conditions>

6) Clinical Recommendations:
- <targeted, evidence-based interventions with mechanism>""",

    "doctor": """You are a clinician writing a circadian health report for a referring physician.

Use clinical language appropriate for a medical doctor: refer to sleep-wake patterns,
circadian misalignment, fragmentation, light hygiene, metabolic and cardiovascular risk
associations. Avoid deep chronobiology jargon but do use standard clinical terms.
Include ICD-adjacent language where appropriate (e.g., insomnia, hypersomnia, circadian
rhythm sleep-wake disorder).

Required output structure (use these exact headings):

Summary: <1–2 sentences: overall clinical impression>

1) Key Findings:
- <3–6 bullets: abnormal or notable metrics in clinical terms>

2) Symptom & Risk Associations (evidence-supported):
- <3–5 bullets: pattern → likely symptoms → medium/long-term risks>

3) Relevant Literature:
- <2–4 bullets citing key evidence from the abstracts>

4) Management Recommendations:
- <3–5 bullets: practical, timed interventions; note any referral indications>

Safety note: <1 sentence>""",

    "layperson": """You are a circadian health coach writing a plain-language report for a patient.

Rules:
- Plain language. No acronyms, no jargon. If you must mention a term, explain it in plain words.
- Do NOT diagnose. Use cautious language: "can be linked to", "may affect", "is often associated with".
- Use short sentences, bullet points, and everyday analogies.
- Be encouraging and practical.

Required output structure (use these exact headings):

Summary: <1–2 sentences: plain-English overall picture>

1) What looks off (in simple terms):
- <2–5 bullets>

2) What looks good — keep doing this:
- <2–5 bullets>

3) Your 7-day action plan:
- <4–6 bullets, each starts with a verb, include approximate timing>

4) How these patterns can affect you:
- <3–5 bullets: pattern → everyday symptom → longer-term risk, in simple words>

Safety note: <1 sentence encouraging professional help if symptoms are significant>""",
}


# ---------------------------------------------------------------------------
# Agent node functions
# ---------------------------------------------------------------------------

def agent1_data_summariser(state: PipelineState) -> PipelineState:
    _notify(state, "🔬 Agent 1/5: Summarising your circadian data...")
    summary = _chat(
        model_name=state["model"],
        system=_AGENT1_SYSTEM,
        user=f"# Actigraphy Metrics\n{state['compact_report']}\n\n"
             "Summarise these metrics for a downstream literature researcher.",
        temperature=0.2,
    )
    return {**state, "data_summary": summary}


def agent2_keyword_extractor(state: PipelineState) -> PipelineState:
    _notify(state, "🔑 Agent 2/5: Extracting literature search terms...")
    fast_model = "llama3.2"
    anamnesis = state.get("anamnesis", "").strip()

    # Build user message — add anamnesis addendum when available
    base_user = (
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        "Output JSON lines query intents."
    )
    if anamnesis:
        base_user = (
            f"# Clinical Data Summary\n{state['data_summary']}\n"
            + _AGENT2_ANAMNESIS_ADDENDUM.format(anamnesis=anamnesis)
        )

    try:
        queries_text = _chat(
            model_name=fast_model,
            system=_AGENT2_SYSTEM,
            user=base_user,
            temperature=0.1,
        )
    except Exception:
        queries_text = _chat(
            model_name=state["model"],
            system=_AGENT2_SYSTEM,
            user=base_user,
            temperature=0.1,
        )
    queries = _parse_structured_queries(queries_text)
    if not queries:
        queries = [
            {
                "topic": "circadian rhythm actigraphy",
                "population": "humans",
                "context": "sleep irregularity",
                "expected_link": "circadian instability and daytime symptoms",
            },
            {
                "topic": "light exposure melanopic",
                "population": "humans",
                "context": "phase alignment",
                "expected_link": "light timing and circadian phase",
            },
        ]
    return {**state, "search_queries": queries}


def agent3_literature_search(state: PipelineState) -> PipelineState:
    _notify(state, "📚 Agent 3/5: Searching PubMed for relevant literature...")
    cfg = RetrievalConfig(
        years_back=10 if state.get("audience") != "expert" else 15,
        adults_only=state.get("audience") == "doctor",
    )
    evidence_items = search_pubmed(state["search_queries"], config=cfg)
    if evidence_items:
        _notify(state, "🔍 Agent 3/5: Running secondary relevance judge...")
        # Stage 1 lexical ranking is done by search_pubmed; stage 2 is lightweight LLM judge.
        keep_pmids = _llm_keep_pmids(
            evidence_items=evidence_items,
            queries=state["search_queries"],
            summary=state.get("data_summary", ""),
            fast_model="llama3.2",
            fallback_model=state["model"],
        )
        if keep_pmids:
            evidence_items = [x for x in evidence_items if str(x.get("pmid")) in keep_pmids]
    raw_abstracts = evidence_to_text(evidence_items)
    pmids = [str(x.get("pmid")) for x in evidence_items if x.get("pmid")]
    return {**state, "raw_abstracts": raw_abstracts, "pmid_list": pmids, "evidence_items": evidence_items}


def agent4_literature_synthesiser(state: PipelineState) -> PipelineState:
    _notify(state, "🧪 Agent 4/5: Synthesising literature evidence...")
    user_content = (
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# PubMed Abstracts\n{state['raw_abstracts']}\n\n"
        "Identify relevant findings and produce a 200-word evidence summary."
    )
    lit_summary = _chat(
        model_name=state["model"],
        system=_AGENT4_SYSTEM,
        user=user_content,
        temperature=0.2,
    )
    return {**state, "lit_summary": lit_summary}


_BARE_PMID_RE = re.compile(r"\(\s*PMID(?:\s*[:#-])?\s*\)")
_PMID_WITH_NUM_RE = re.compile(r"PMID\s*[:#-]?\s*(\d+)")


def _sanitize_pmids(report_text: str, allowed_pmids: set[str]) -> str:
    """Remove fabricated and bare PMID citations from report text.

    - Strips bare ``(PMID)`` / ``(PMID:)`` placeholders entirely.
    - Replaces ``(PMID 12345)`` whose ID is not in ``allowed_pmids`` with
      ``(no direct evidence found)``.
    """
    text = _BARE_PMID_RE.sub("(no direct evidence found)", report_text)

    def _replace_citation(match: re.Match) -> str:
        body = match.group(0)
        cited = _PMID_WITH_NUM_RE.findall(body)
        kept = [pid for pid in cited if pid in allowed_pmids]
        if not cited:
            return "(no direct evidence found)"
        if not kept:
            return "(no direct evidence found)"
        return "(" + "; ".join(f"PMID {pid}" for pid in kept) + ")"

    text = re.sub(r"\([^()]*PMID[^()]*\)", _replace_citation, text)
    return text


def agent5_report_writer(state: PipelineState) -> PipelineState:
    audience = state.get("audience", "layperson")
    audience_label = {
        "expert": "Circadian Expert",
        "doctor": "Medical Doctor",
        "layperson": "General User",
    }.get(audience, "General User")
    _notify(state, f"✍️ Agent 5/5: Writing final report for {audience_label}...")
    system_prompt = _AGENT5_AUDIENCES.get(audience, _AGENT5_AUDIENCES["layperson"])

    evidence_items = state.get("evidence_items") or []
    has_evidence = bool(evidence_items)

    user_content = (
        f"# Actigraphy Data Context\n{state['compact_report']}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Supporting Literature Evidence\n{state['lit_summary']}\n\n"
        f"# Evidence Items (use PMIDs from here only)\n{json.dumps(evidence_items, ensure_ascii=False)}\n\n"
    )
    symptom_table = state.get("symptom_metric_table", "").strip()
    if symptom_table:
        user_content += (
            f"# Symptom-Metric Correlation (Agent 6 output)\n{symptom_table}\n\n"
            "When writing the report, include a section titled \'Symptom-Metric Correlation\' "
            "that incorporates the table above and highlights any unexplained symptoms.\n\n"
        )
    if has_evidence:
        user_content += (
            "Write the final report now.\n"
            "Citation rules — STRICT:\n"
            "- Every evidence-backed claim must cite a real PMID in parentheses, e.g. (PMID 12345678).\n"
            "- ONLY use PMIDs that appear in the Evidence Items list above. Never invent or guess a PMID.\n"
            "- NEVER write a bare placeholder like '(PMID)' with no number. If you have no PMID for a claim, "
            "write '(no direct evidence found)' instead, or omit the claim."
        )
    else:
        user_content += (
            "Write the final report now.\n"
            "IMPORTANT — no PubMed evidence was retrieved for this case:\n"
            "- Do NOT cite any PMIDs anywhere in the report.\n"
            "- Do NOT write '(PMID)', '(PMID: ...)', or any placeholder suggesting a citation.\n"
            "- For any claim that would normally need literature support, either omit it or label it as "
            "'(no direct evidence found)'.\n"
            "- You may still report data-driven findings from the Clinical Data Summary."
        )

    final_report = _chat(
        model_name=state["model"],
        system=system_prompt,
        user=user_content,
        temperature=0.2,
    )

    # Post-process: scrub bare/fabricated PMID placeholders the model may still emit.
    pmids = state.get("pmid_list") or []
    allowed = {str(p) for p in pmids}
    final_report = _sanitize_pmids(final_report, allowed)

    claim_to_pmid_map: dict[str, list[str]] = {}
    for line in final_report.splitlines():
        if "PMID" in line:
            cited = _PMID_WITH_NUM_RE.findall(line)
            cited = [c for c in cited if c in allowed]
            if cited:
                claim_to_pmid_map[line.strip()[:180]] = cited

    if pmids:
        ref_lines = ["\n\n---\nReferences (PubMed):"]
        for i, pmid in enumerate(pmids, start=1):
            ref_lines.append(f"{i}. PMID {pmid} — https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        final_report = final_report + "\n".join(ref_lines)
    return {**state, "final_report": final_report, "claim_to_pmid_map": claim_to_pmid_map}


def agent6_symptom_metric_linker(state: PipelineState) -> PipelineState:
    """Run only when anamnesis is present. Maps symptoms → metric changes → literature."""
    _notify(state, "🩺 Agent 6/6: Linking patient symptoms to metric changes...")
    user_content = (
        f"# Patient Anamnesis\n{state['anamnesis']}\n\n"
        f"# Clinical Data Summary (metric changes)\n{state['data_summary']}\n\n"
        f"# PubMed Abstracts\n{state['raw_abstracts']}\n\n"
        "Produce the Symptom-Metric Correlation Table as instructed."
    )
    table = _chat(
        model_name=state["model"],
        system=_AGENT6_SYSTEM,
        user=user_content,
        temperature=0.1,
    )
    return {**state, "symptom_metric_table": table}


# ---------------------------------------------------------------------------
# Build and compile the LangGraph graph (once at module load)
# ---------------------------------------------------------------------------

def _route_after_synthesis(state: PipelineState) -> str:
    """Conditional router: if anamnesis is present, run Agent 6 before the report writer."""
    if state.get("anamnesis", "").strip():
        return "symptom_metric_linker"
    return "report_writer"


def _build_graph():
    g = StateGraph(PipelineState)
    g.add_node("data_summariser",        agent1_data_summariser)
    g.add_node("keyword_extractor",      agent2_keyword_extractor)
    g.add_node("literature_search",      agent3_literature_search)
    g.add_node("literature_synthesiser", agent4_literature_synthesiser)
    g.add_node("symptom_metric_linker",  agent6_symptom_metric_linker)
    g.add_node("report_writer",          agent5_report_writer)

    g.set_entry_point("data_summariser")
    g.add_edge("data_summariser",       "keyword_extractor")
    g.add_edge("keyword_extractor",     "literature_search")
    g.add_edge("literature_search",     "literature_synthesiser")
    g.add_conditional_edges(
        "literature_synthesiser",
        _route_after_synthesis,
        {"symptom_metric_linker": "symptom_metric_linker", "report_writer": "report_writer"},
    )
    g.add_edge("symptom_metric_linker",  "report_writer")
    g.add_edge("report_writer",          END)
    return g.compile()


_GRAPH = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_circadian_report(
    json_filepath: str,
    model: str = "phi4:14b",
    audience: str = "layperson",
    anamnesis: str = "",
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Run the pipeline and return the final report string.

    Args:
        json_filepath:     Path to the circadian JSON report file.
        model:             Ollama model for Agents 1, 4, 5, and 6.
        audience:          "expert" | "doctor" | "layperson"
        anamnesis:         Optional patient history / symptom text (doctor/expert only).
                           When non-empty, activates Agent 6 (symptom-metric linker) and
                           mixed PubMed query generation.
        progress_callback: Optional callable(str) for live progress updates.

    Returns:
        Final report as a string, or an error message starting with "Error".
    """
    try:
        with open(json_filepath, "r") as f:
            report_data = json.load(f)
    except Exception as e:
        return f"Error loading JSON file: {e}"

    compact = _compact_report_for_llm(report_data)
    initial_state: PipelineState = {
        "json_filepath":       json_filepath,
        "compact_report":      compact,
        "data_summary":        "",
        "search_queries":      [],
        "raw_abstracts":       "",
        "pmid_list":           [],
        "evidence_items":      [],
        "lit_summary":         "",
        "anamnesis":           anamnesis.strip(),
        "symptom_metric_table": "",
        "claim_to_pmid_map":   {},
        "audience":            audience,
        "final_report":        "",
        "model":               model,
        "progress_callback":   progress_callback,
    }
    try:
        final_state = _GRAPH.invoke(initial_state)
        return final_state["final_report"]
    except Exception as e:
        # deterministic fallback: no narrative hallucination, only data/evidence summary.
        fallback = (
            "Fallback report (deterministic):\n\n"
            f"Data summary:\n{initial_state['compact_report'][:3000]}\n\n"
            "Evidence summary:\nNo reliable LLM synthesis available for this run."
        )
        log_event("ai_pipeline_fallback", error=str(e))
        return fallback


def get_intermediate_results(
    json_filepath: str,
    model: str = "phi4:14b",
    audience: str = "layperson",
    anamnesis: str = "",
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    """
    Run the pipeline and return ALL intermediate outputs for display in the UI.

    Returns a dict with keys:
      data_summary, search_queries, raw_abstracts, pmid_list, lit_summary,
      symptom_metric_table, final_report
    or {"error": "..."} on failure.
    """
    try:
        with open(json_filepath, "r") as f:
            report_data = json.load(f)
    except Exception as e:
        return {"error": f"Error loading JSON file: {e}"}

    compact = _compact_report_for_llm(report_data)
    initial_state: PipelineState = {
        "json_filepath":        json_filepath,
        "compact_report":       compact,
        "data_summary":         "",
        "search_queries":       [],
        "raw_abstracts":        "",
        "pmid_list":            [],
        "evidence_items":       [],
        "lit_summary":          "",
        "anamnesis":            anamnesis.strip(),
        "symptom_metric_table": "",
        "claim_to_pmid_map":    {},
        "audience":             audience,
        "final_report":         "",
        "model":                model,
        "progress_callback":    progress_callback,
    }
    try:
        final_state = _GRAPH.invoke(initial_state)
        agent_trace = {
            "agent1_data_summariser": {
                "input": {
                    "compact_report": initial_state["compact_report"],
                    "model": initial_state["model"],
                },
                "output": {
                    "data_summary": final_state["data_summary"],
                },
            },
            "agent2_keyword_extractor": {
                "input": {
                    "data_summary": final_state["data_summary"],
                    "anamnesis": initial_state["anamnesis"],
                },
                "output": {
                    "search_queries": final_state["search_queries"],
                },
            },
            "agent3_literature_search": {
                "input": {
                    "search_queries": final_state["search_queries"],
                },
                "output": {
                    "raw_abstracts": final_state["raw_abstracts"],
                    "pmid_list": final_state["pmid_list"],
                    "evidence_items": final_state.get("evidence_items", []),
                },
            },
            "agent4_literature_synthesiser": {
                "input": {
                    "data_summary": final_state["data_summary"],
                    "raw_abstracts": final_state["raw_abstracts"],
                },
                "output": {
                    "lit_summary": final_state["lit_summary"],
                },
            },
            "agent5_report_writer": {
                "input": {
                    "compact_report": final_state["compact_report"],
                    "data_summary": final_state["data_summary"],
                    "lit_summary": final_state["lit_summary"],
                    "symptom_metric_table": final_state.get("symptom_metric_table", ""),
                    "pmid_list": final_state["pmid_list"],
                    "claim_to_pmid_map": final_state.get("claim_to_pmid_map", {}),
                    "audience": final_state["audience"],
                },
                "output": {
                    "final_report": final_state["final_report"],
                },
            },
        }

        if final_state.get("anamnesis", "").strip():
            agent_trace["agent6_symptom_metric_linker"] = {
                "input": {
                    "anamnesis": final_state["anamnesis"],
                    "data_summary": final_state["data_summary"],
                    "raw_abstracts": final_state["raw_abstracts"],
                },
                "output": {
                    "symptom_metric_table": final_state.get("symptom_metric_table", ""),
                },
            }

        return {
            "json_filepath":         initial_state["json_filepath"],
            "audience":              final_state["audience"],
            "model":                 final_state["model"],
            "anamnesis":             final_state.get("anamnesis", ""),
            "data_summary":         final_state["data_summary"],
            "search_queries":       final_state["search_queries"],
            "raw_abstracts":        final_state["raw_abstracts"],
            "pmid_list":            final_state["pmid_list"],
            "evidence_items":       final_state.get("evidence_items", []),
            "lit_summary":          final_state["lit_summary"],
            "symptom_metric_table": final_state["symptom_metric_table"],
            "claim_to_pmid_map":    final_state.get("claim_to_pmid_map", {}),
            "final_report":         final_state["final_report"],
            "agent_trace":          agent_trace,
        }
    except Exception as e:
        fallback_report = (
            "Fallback report (deterministic):\n\n"
            f"Data summary:\n{initial_state['compact_report'][:3000]}\n\n"
            "Evidence summary:\nNo reliable LLM synthesis available for this run."
        )
        log_event("ai_pipeline_fallback", error=str(e))
        return {
            "json_filepath": initial_state["json_filepath"],
            "audience": audience,
            "model": model,
            "anamnesis": anamnesis,
            "data_summary": "",
            "search_queries": [],
            "raw_abstracts": "No PubMed abstracts found for the given search terms.",
            "pmid_list": [],
            "evidence_items": [],
            "lit_summary": "",
            "symptom_metric_table": "",
            "claim_to_pmid_map": {},
            "final_report": fallback_report,
            "agent_trace": {},
            "error": f"Error during pipeline: {e}",
        }


def save_analysis(analysis_text: str, filename: str = "llm_analysis.txt") -> str:
    """Save the LLM analysis to a text file. Returns full path."""
    filepath = os.path.join(os.getcwd(), filename)
    with open(filepath, "w") as f:
        f.write(analysis_text)
    return filepath


def continue_conversation(
    user_question: str,
    json_filepath: str,
    conversation_history: list[dict],
    model: str = "phi4:14b",
    anamnesis: str = "",
) -> str:
    """
    Continue a follow-up conversation about the circadian report.
    Uses the main model directly (no pipeline re-run needed for follow-ups).

    Args:
        user_question:        The follow-up question.
        json_filepath:        Path to the JSON report file.
        conversation_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        model:                Ollama model name.
        anamnesis:            Optional patient anamnesis for context.

    Returns:
        Response string, or error message starting with "Error".
    """
    try:
        with open(json_filepath, "r") as f:
            report_data = json.load(f)
    except Exception as e:
        return f"Error loading report data: {e}"

    compact = _compact_report_for_llm(report_data)

    anamnesis_context = ""
    if anamnesis and anamnesis.strip():
        anamnesis_context = (
            f"\n\nPatient anamnesis on file:\n{anamnesis.strip()}\n"
            "When answering, take the reported symptoms into account and link them to "
            "the circadian metric changes where relevant."
        )

    system_prompt = (
        "You are a circadian health expert helping a user understand their actigraphy report. "
        "Answer the user's question accurately based on the available data. "
        "Be concise (180 words max unless the user asks for more). "
        "Use cautious clinical language — do not diagnose. "
        "Structure your answer as:\n"
        "- Direct answer (2–4 sentences)\n"
        "- What in the data suggests this:\n"
        "- What to try next:\n"
        "- What it can be linked to (if relevant):"
        + anamnesis_context
    )

    messages: list[SystemMessage | HumanMessage | AIMessage] = []
    messages.append(SystemMessage(content=system_prompt))
    for msg in conversation_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    current_msg = (
        f"User question: {user_question}\n\n"
        f"# Available report data:\n{compact}"
    )
    messages.append(HumanMessage(content=current_msg))

    try:
        llm = ChatOllama(model=model, temperature=0.3)
        response = llm.invoke(messages)
        content = response.content
        if isinstance(content, str):
            return content.strip()
        return str(content)
    except Exception as e:
        return f"Error during conversation: {e}\n\nPlease ensure Ollama is running and the model '{model}' is available."
