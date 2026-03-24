"""
5-Agent LangGraph pipeline for circadian medicine report analysis.

Pipeline:
  JSON Report
      ↓
  [Agent 1: Data Summariser]        ← LM Studio (OpenAI-compatible local API)
      → clinical metric summary (~400 words)
      ↓
  [Agent 2: Keyword Extractor]      ← LM Studio (fast model)
      → 3-5 MeSH-style PubMed queries
      ↓
  [Agent 3: Literature Search]      ← PubMed E-utilities API (no patient data sent)
      → raw abstracts (capped at ~8 000 chars)
      ↓
  [Agent 4: Literature Synthesiser] ← LM Studio
      → concise evidence summary (~200 words)
      ↓
  [Agent 5: Report Writer]          ← LM Studio, audience-aware
      → final structured report

Privacy note: PubMed queries are sent to PubMed. LLM prompts are sent to the
configured LM Studio endpoint (local by default at 127.0.0.1).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, TypedDict, Callable

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from pydantic import SecretStr

from tools.pubmed_search import search_pubmed


# ---------------------------------------------------------------------------
# Shared pipeline state
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    """State object passed between all agents."""
    json_filepath: str
    compact_report: str           # Agent 1 input (flattened metrics)
    data_summary: str             # Agent 1 output
    search_queries: list[str]     # Agent 2 output
    raw_abstracts: str            # Agent 3 output
    pmid_list: list[str]          # Agent 3 output — PubMed IDs of retrieved articles
    lit_summary: str              # Agent 4 output
    anamnesis: str                # Doctor/Expert input — patient history & symptoms
    symptom_metric_table: str     # Agent 6 output — symptom → metric → literature map
    audience: str                 # "expert" | "doctor" | "layperson"
    final_report: str             # Agent 5 output
    model: str                    # LM Studio model name for main agents
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


_LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
_LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
_DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", "marcoroni-neural-chat-7b-v2_gsm8k_merged")


def _build_llm(model_name: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=SecretStr(_LM_STUDIO_API_KEY),
        base_url=_LM_STUDIO_BASE_URL,
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    return str(content).strip()


# ---------------------------------------------------------------------------
# Query validation helpers (Task 1)
# ---------------------------------------------------------------------------

_QUERY_STRIP_RE = re.compile(
    r'^(?:\d+[.):\-]\s*|[-•*–—]\s*|["\'])',  # leading numbering / bullets / quotes
    re.UNICODE,
)


def _clean_queries(raw_text: str) -> list[str]:
    """
    Parse LLM output into clean PubMed-ready search queries.

    Removes common LLM-output artefacts (numbering, bullets, markdown quotes)
    and validates that each query is a plausible MeSH-style phrase (2–8 words,
    under 100 characters). Returns up to 5 cleaned queries.
    """
    queries: list[str] = []
    for line in raw_text.splitlines():
        q = _QUERY_STRIP_RE.sub("", line).strip().strip("\'\"")
        # Must look like a keyword phrase: 2–8 words, reasonable length
        if 2 <= len(q.split()) <= 8 and 5 < len(q) <= 100:
            queries.append(q)
        if len(queries) == 5:
            break
    return queries


# ---------------------------------------------------------------------------
# Abstract relevance filter (Task 2)
# ---------------------------------------------------------------------------

_RELEVANCE_SYSTEM = """You are a biomedical relevance filter.
You will receive PubMed abstracts and the search queries that retrieved them.
Your task: return ONLY the abstract blocks that are genuinely relevant to
circadian rhythms, sleep, actigraphy, light exposure, or chronobiology.

Rules:
- Keep each block that clearly relates to the clinical context.
- Remove blocks that are off-topic due to keyword ambiguity.
- Preserve each kept block exactly as given (PMID, TITLE, ABSTRACT lines intact),
  separated by ---
- If all blocks are relevant, return them unchanged.
- If none are relevant, return: No relevant abstracts found.
- Output ONLY the filtered blocks — no commentary."""


def _filter_relevant_abstracts(
    abstracts: str,
    queries: list[str],
    fast_model: str,
) -> str:
    """
    Use a fast local LLM to remove PubMed abstracts that are not relevant
    to the circadian/sleep context implied by the search queries.
    Falls back to the original text if the model call fails.
    """
    if not abstracts or abstracts.startswith("No PubMed"):
        return abstracts
    user_content = (
        f"Search queries: {'; '.join(queries)}\n\n"
        f"---\n\n{abstracts}"
    )
    try:
        filtered = _chat(
            model_name=fast_model,
            system=_RELEVANCE_SYSTEM,
            user=user_content,
            temperature=0.0,
        )
        if filtered and len(filtered) > 80:
            return filtered
    except Exception:
        pass
    return abstracts


def _chat(model_name: str, system: str, user: str, temperature: float = 0.2) -> str:
    llm = _build_llm(model_name=model_name, temperature=temperature)
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return _content_to_text(response.content)


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
Given a clinical summary of actigraphy data, extract PubMed search queries.

Rules:
- Use MeSH-style keyword phrases (2–5 words per query).
- Focus on the most abnormal or clinically notable findings from the summary.
- Each query should target a distinct aspect of the findings.
- Output ONLY the queries, one per line, no numbering, no explanation.
- Example format:
circadian rhythm sleep irregularity actigraphy
interdaily stability actigraphy cardiovascular risk
light exposure melanopic circadian alignment"""

_AGENT2_ANAMNESIS_ADDENDUM = """
Additional context — Patient anamnesis (reported symptoms/history):
{anamnesis}

Because an anamnesis is available, generate a MIXED query set:
- 3 queries focused on the most abnormal circadian/sleep metrics (as above)
- 2 additional queries that COMBINE a reported symptom with a relevant metric change
  (e.g., "sleep fragmentation fatigue daytime", "circadian misalignment depression mood")
Total: exactly 5 queries, one per line, no numbering."""

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
    fast_model = os.getenv("LM_STUDIO_FAST_MODEL", state["model"])
    anamnesis = state.get("anamnesis", "").strip()

    # Build user message — add anamnesis addendum when available
    base_user = (
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        "Output PubMed search queries, one per line."
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
    # clean and validate LLM-generated queries before they hit PubMed
    queries = _clean_queries(queries_text)
    if not queries:
        queries = ["circadian rhythm actigraphy", "sleep irregularity health outcomes"]
    return {**state, "search_queries": queries}


def agent3_literature_search(state: PipelineState) -> PipelineState:
    _notify(state, "📚 Agent 3/5: Searching PubMed for relevant literature...")
    # Task 3: search_pubmed now returns (text, pmids)
    abstracts, pmids = search_pubmed(state["search_queries"])
    if not abstracts:
        abstracts = "No PubMed abstracts found for the given search terms."
        pmids = []
    else:
        # Task 2: filter out off-topic abstracts using a fast local LLM
        _notify(state, "🔍 Agent 3/5: Validating relevance of retrieved abstracts...")
        abstracts = _filter_relevant_abstracts(
            abstracts,
            state["search_queries"],
            fast_model=os.getenv("LM_STUDIO_FAST_MODEL", state["model"]),
        )
    return {**state, "raw_abstracts": abstracts, "pmid_list": pmids}


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


def agent5_report_writer(state: PipelineState) -> PipelineState:
    audience = state.get("audience", "layperson")
    audience_label = {
        "expert": "Circadian Expert",
        "doctor": "Medical Doctor",
        "layperson": "General User",
    }.get(audience, "General User")
    _notify(state, f"✍️ Agent 5/5: Writing final report for {audience_label}...")
    system_prompt = _AGENT5_AUDIENCES.get(audience, _AGENT5_AUDIENCES["layperson"])

    user_content = (
        f"# Actigraphy Data Context\n{state['compact_report']}\n\n"
        f"# Clinical Data Summary\n{state['data_summary']}\n\n"
        f"# Supporting Literature Evidence\n{state['lit_summary']}\n\n"
    )
    symptom_table = state.get("symptom_metric_table", "").strip()
    if symptom_table:
        user_content += (
            f"# Symptom-Metric Correlation (Agent 6 output)\n{symptom_table}\n\n"
            "When writing the report, include a section titled \'Symptom-Metric Correlation\' "
            "that incorporates the table above and highlights any unexplained symptoms.\n\n"
        )
    user_content += "Write the final report now."

    final_report = _chat(
        model_name=state["model"],
        system=system_prompt,
        user=user_content,
        temperature=0.2,
    )
    # append a references section with PubMed links for cited PMIDs
    pmids = state.get("pmid_list") or []
    if pmids:
        ref_lines = ["\n\n---\nReferences (PubMed):"]
        for i, pmid in enumerate(pmids, start=1):
            ref_lines.append(f"{i}. PMID {pmid} — https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        final_report = final_report + "\n".join(ref_lines)
    return {**state, "final_report": final_report}


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
    model: str = _DEFAULT_MODEL,
    audience: str = "layperson",
    anamnesis: str = "",
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Run the pipeline and return the final report string.

    Args:
        json_filepath:     Path to the circadian JSON report file.
        model:             LM Studio model for Agents 1, 4, 5, and 6.
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
        "lit_summary":         "",
        "anamnesis":           anamnesis.strip(),
        "symptom_metric_table": "",
        "audience":            audience,
        "final_report":        "",
        "model":               model,
        "progress_callback":   progress_callback,
    }
    try:
        final_state = _GRAPH.invoke(initial_state)
        return final_state["final_report"]
    except Exception as e:
        return f"Error during pipeline: {e}"


def get_intermediate_results(
    json_filepath: str,
    model: str = _DEFAULT_MODEL,
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
        "lit_summary":          "",
        "anamnesis":            anamnesis.strip(),
        "symptom_metric_table": "",
        "audience":             audience,
        "final_report":         "",
        "model":                model,
        "progress_callback":    progress_callback,
    }
    try:
        final_state = _GRAPH.invoke(initial_state)
        return {
            "data_summary":         final_state["data_summary"],
            "search_queries":       final_state["search_queries"],
            "raw_abstracts":        final_state["raw_abstracts"],
            "pmid_list":            final_state["pmid_list"],
            "lit_summary":          final_state["lit_summary"],
            "symptom_metric_table": final_state["symptom_metric_table"],
            "final_report":         final_state["final_report"],
        }
    except Exception as e:
        return {"error": f"Error during pipeline: {e}"}


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
    model: str = _DEFAULT_MODEL,
    anamnesis: str = "",
) -> str:
    """
    Continue a follow-up conversation about the circadian report.
    Uses the main model directly (no pipeline re-run needed for follow-ups).

    Args:
        user_question:        The follow-up question.
        json_filepath:        Path to the JSON report file.
        conversation_history: List of {"role": "user"|"assistant", "content": "..."} dicts.
        model:                LM Studio model name.
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

    messages: list[SystemMessage | HumanMessage | AIMessage] = [SystemMessage(content=system_prompt)]
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
        llm = _build_llm(model_name=model, temperature=0.3)
        response = llm.invoke(messages)
        return _content_to_text(response.content)
    except Exception as e:
        return (
            f"Error during conversation: {e}\n\n"
            f"Please ensure LM Studio is running at {_LM_STUDIO_BASE_URL} and the model '{model}' is loaded."
        )
