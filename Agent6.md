
## Agent 6 — How it works

### When does it run?

It only runs when the doctor/expert has filled in the anamnesis text box. The LangGraph router `_route_after_synthesis` checks this:

```
after Agent 4 finishes
    ↓
anamnesis empty? → skip to Agent 5
anamnesis present? → run Agent 6, then Agent 5
```

---

### What data does it receive?

Agent 6 gets **three pieces of data** from `PipelineState`, all already computed by earlier agents:

| Source | State field | What it contains |
|---|---|---|
| Doctor types it in | `anamnesis` | Free text: *"fatigue, poor concentration, mood changes in the afternoon"* |
| Agent 1 output | `data_summary` | LLM-written clinical narrative of the metric changes, e.g. *"SRI dropped from 78 to 61 (Δ=−17), IV increased..."* |
| Agent 3 output | `raw_abstracts` | PubMed abstract texts, each prefixed with its `PMID:` |

It does **not** see the raw JSON numbers — it sees Agent 1's plain-language summary of those numbers, which already contains all the Δ values in clinical language.

---

### How does it combine symptom → metric?

The LLM receives all three inputs in one prompt. For **each symptom** in the anamnesis it is asked to find:

1. **The most relevant metric change** from the data summary (e.g. *"IV ↑ from 0.48 to 0.71, indicating increased intraday fragmentation"*)
2. **A 1-sentence supporting finding** from a PubMed abstract — or *"No direct evidence found"* if nothing matches
3. **The PMID** of that abstract

The output is a strict Markdown table:

```
|Symptom|Relevant Metric Change|Evidence Support|PMID|
|---|---|---|---|
|Fatigue|IV ↑ 0.48→0.71 (more fragmentation)|High IV is associated with daytime fatigue in older adults|38291045|
|Poor concentration|SRI ↓ 78→61 (less regularity)|Sleep irregularity linked to impaired cognitive function|37104822|
|Afternoon mood dip|Cosinor acrophase shift −2.3 h|Phase delay of activity rhythm associated with depressive symptoms|—|
```

Followed by:
```
Unexplained symptoms (no supporting literature found):
- [any symptom with no abstract match]
```

---

### What happens with this output?

The `symptom_metric_table` string (the table above) flows into `PipelineState` and is then passed to **Agent 5**, which is instructed to embed it as a dedicated **"Symptom-Metric Correlation"** section in the final report. The table is also shown separately in the UI in the collapsible "pipeline intermediates" panel.

---

### Key design choices

- **Temperature = 0.1** — lower than other agents, because the output is a structured table where consistency matters
- **No new PubMed search** — it reuses the abstracts already fetched by Agent 3 (the mixed queries from Agent 2 already included symptom+metric combos, so the abstracts should contain relevant evidence)
- **Unexplained symptoms are surfaced explicitly** — if a symptom has no literature match, the doctor is told, rather than the gap being silently ignored