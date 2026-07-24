# Comparison: llm_pipeline_Gemeni vs Claude vs ChatGPT

## Similarities — what all three notebooks share

| Aspect | All three |
|---|---|
| LLM backend | Local Ollama via `ChatOllama` — no cloud API |
| Core model roles | `data_summariser` → `qwen3.5:9b`; `pubmed_query_planner` → `llama3.2` / fallback `gemma4`; `literature_synthesiser` & `report_writer` → `gemma4` / fallback `qwen3.5:9b` |
| Graph framework | LangGraph `StateGraph` with `MemorySaver` checkpointing |
| Node set (base) | data_summariser → pubmed_query_planner → pubmed_retriever → relevance_judge → literature_synthesiser → report_writer → tuning_memory_writer |
| Prompts origin | `AGENT1/2/4/6/RELEVANCE_SYSTEM` loaded from `tools/llm_conversation.py` |
| PMID safety | `_sanitize_pmids()` strips hallucinated citations in all three |
| Conditional routing | If `ANAMNESIS` is set, `symptom_metric_linker` is inserted before `report_writer` |
| Persistent memory | `llm_pipeline_tuning_memory.json` shared across all three |

---

## Differences — by dimension

### 1. PubMed retrieval configuration

| Parameter | Gemeni | Claude | ChatGPT |
|---|---|---|---|
| `retmax_per_query` | 25 | 30 | **40** |
| `keep_per_query` | 8 | **10** | 8 |
| `max_total_items` | 25 | **50** | 35 |
| `years_back` | 15 | 10 | **20** |

**Effect:** Claude pulls up to 50 unique papers per run; ChatGPT searches the widest date window; Gemeni is the most conservative. More papers = larger context for downstream LLM nodes = longer inference time.

---

### 2. Graph nodes (pipeline architecture)

| Node | Gemeni | Claude | ChatGPT |
|---|---|---|---|
| `data_summariser` | ✓ | ✓ | ✓ |
| `construct_mapper` | — | **✓** | — |
| `deterministic_change_interpreter` | — | — | **✓** |
| `pubmed_query_planner` | ✓ | ✓ | ✓ |
| `pubmed_retriever` | ✓ | ✓ | ✓ |
| `relevance_judge` | ✓ | ✓ | ✓ |
| `literature_synthesiser` | ✓ | ✓ | ✓ |
| `symptom_metric_linker` | conditional | conditional | conditional |
| `report_writer` | ✓ | ✓ | ✓ |
| `tuning_memory_writer` | ✓ | ✓ | ✓ |

**Effect:** Claude and ChatGPT have one extra deterministic step before the LLM query planner. That step is fast (pure Python) but changes what information every subsequent node receives.

---

### 3. Deterministic metric-to-concept translation

**Gemeni** — none. The LLM query planner is given the raw data summary plus hard-coded search rules (no quotes, keep terms broad). Fallback defaults are generic circadian queries.

**Claude** — uses `derive_constructs()` with `METRIC_CONSTRUCT_MAP`. Reads `delta_z` from the database JSON, maps each metric (SRI, IS, IV, RA, etc.) to a clinical construct string (e.g., "sleep irregularity"), and gates on a Z-score threshold (`CONSTRUCT_Z_THRESHOLD = 1.0`). Only salient changes become queries.

**ChatGPT** — uses `interpret_metric_changes()` with `METRIC_DIRECTION_ONTOLOGY`. Parses the text of the data summary for direction words (increase/decrease/delay/advance) and matches them to a detailed ontology that includes `query_terms` and `avoid_primary_terms` per metric per direction. Both base + LLM queries are merged and deduplicated.

**Effect on results:** Gemeni produces more generic PubMed queries; Claude and ChatGPT produce concept-grounded queries. This changes which papers are retrieved and therefore the entire report content.

---

### 4. Relevance filtering strategy

**Gemeni** — binary: if the judge returns a `keep_pmids` set, filter to that set. If it returns nothing, keep everything.

**Claude** — scored ranking: judge returns `{pmid, construct_match 0–3, outcome_relevance 0–3, study_quality 0–3}`. Score = `construct_match×2 + outcome_relevance + study_quality`. Items with `construct_match = 0` are dropped. Top-N (`KEEP_TOP_N_AFTER_JUDGING = 15`) are kept.

**ChatGPT** — soft floor: if judge returns fewer than 8 PMIDs, it bypasses the judge and keeps the top 8–18 items by position instead.

**Effect on results:** Claude produces the most aggressively filtered, construct-matched evidence. ChatGPT is the most conservative about over-filtering. Gemeni can silently drop everything if the judge is too strict.

---

### 5. Fallback retrieval

**Gemeni** — single retrieval pass only.

**Claude** — single retrieval pass, but relies on construct-anchored queries to be specific enough.

**ChatGPT** — if fewer than 10 items are returned, a second retrieval pass fires using `build_fallback_queries_from_interpretations()` and the results are merged and deduplicated.

**Effect on inference time:** ChatGPT can make twice as many PubMed API calls in the same run, adding latency.

---

### 6. Literature synthesis prompt

**Gemeni** — instructs the LLM to "synthesize a cohesive 200-word narrative, not a list." Generic instruction targeting narrative prose.

**Claude** — provides a per-construct evidence pack (pre-matched by keyword). Instructs the LLM to write exactly one paragraph per construct. Prompt format is `## ConstructName — paragraph (PMID xxx)`.

**ChatGPT** — injects `INTEGRATED_SYNTHESIS_ADDENDUM` that explicitly forbids the "Study A found X. Study B found Y." pattern and gives a positive example of integrated prose. Max 220 words.

**Effect on results:** Claude output is the most structured (one paragraph per clinical finding). ChatGPT output aims for the most integrated narrative. Gemeni output has the loosest structure.

---

### 7. Report writer prompts and length limits

| | Gemeni | Claude | ChatGPT |
|---|---|---|---|
| Doctor word limit | 250 words (shared) | **250–350 words**, strict section headers | **170 words** maximum |
| Patient word limit | 250 words (shared) | **150–220 words**, exact section headers | **140 words** maximum |
| Expert word limit | 250 words (shared) | not explicitly overridden | **260 words** maximum |
| Report compression pass | — | — | **✓** (second LLM call if over limit) |
| Reference list | Always appended | Only for doctor/expert (not layperson) | Only for `expert` audience |
| PMID citation in body | Yes (all audiences) | Yes (doctor/expert); layperson gets only a `## Sources` section at end | Only expert gets inline PMIDs |

**Effect on results:** Claude and ChatGPT produce shorter, more audience-adapted reports. ChatGPT can fire an extra `report_writer` LLM call to compress the output — adding latency but enforcing length.

---

### 8. Tuning-memory injection into prompts

**Gemeni** — injects `tuning_memory` into `data_summariser`, `pubmed_query_planner`, `literature_synthesiser`, and `report_writer` prompts.

**Claude** — does not inject tuning memory into node prompts (the data_summariser user prompt drops the tuning memory prefix).

**ChatGPT** — injects `tuning_memory` into `data_summariser`, `pubmed_query_planner`, `literature_synthesiser`, and `report_writer` prompts (same as Gemeni).

**Effect:** Gemeni and ChatGPT are sensitive to the content of prior runs stored in `llm_pipeline_tuning_memory.json`. If that file has noise, it degrades results. Claude is isolated from it.

---

## Summary of why you see different inference times

1. **ChatGPT is slowest when evidence is sparse** — possible double retrieval + compression call.
2. **Claude passes the most evidence downstream** — up to 50 items, so larger LLM contexts.
3. **Gemeni is the most predictable in time** — one retrieval pass, no compression, fixed pipeline.

## Summary of why you see different results

1. **Query quality:** Gemeni = LLM-only; Claude = construct Z-score gated; ChatGPT = ontology-mapped + LLM-merged.
2. **Evidence quality:** Claude filters most aggressively; ChatGPT most conservatively; Gemeni can silently over-filter.
3. **Report structure:** Claude is the most opinionated (exact section headers, format rules); Gemeni is the most permissive.
4. **Report length:** ChatGPT produces shortest output (140–170 words for clinical audiences); Gemeni is the most variable.