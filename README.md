# Circadian Medicine Analysis Suite

A privacy-preserving, AI-augmented web application for clinical circadian rhythm and sleep-wake analysis from wearable actigraphy data.

---

## Overview

**Circadian Medicine Analysis Suite** is a [Streamlit](https://streamlit.io)-based research tool that provides an end-to-end workflow for:

1. Uploading and managing multi-day wrist actigraphy recordings
2. Computing a comprehensive set of validated circadian, sleep, and light-exposure metrics
3. Comparing recordings across multiple time periods (e.g., before/after intervention)
4. Generating structured clinical reports via a 5- or 6-agent AI pipeline that runs **entirely locally** — no patient data ever leaves the machine

It was developed at the **Charité – Universitätsmedizin Berlin, Circadian Medicine Lab**.

---

## Screenshots

> Add screenshots of the main analysis view, comparison tab, and AI report here.

---

## Features

### Actigraphy Metrics

| Domain | Metric | Description |
|--------|--------|-------------|
| **Activity** | IS / IV | Interdaily Stability & Intradaily Variability (rolling 2-day) |
| **Activity** | L5 / M10 / RA | Least-active 5 h, Most-active 10 h, Relative Amplitude |
| **Activity** | Cosinor | Daily mesor, amplitude, acrophase fitted by nonlinear least-squares |
| **Activity** | CPD | Change Point Detection on activity pattern |
| **Sleep** | Sleep Periods | Onset time, offset time, mid-sleep time per night |
| **Sleep** | SRI | Sleep Regularity Index (rolling sliding window) |
| **Sleep** | Sleep–Light Exposure | Light-level classification during sleep/wake transition windows |
| **Sleep** | CPD | Circular change-point detection on mid-sleep phase |
| **Light** | IS / IV | Interdaily Stability & Intradaily Variability of light exposure |
| **Light** | L5 / M10 / RA | Darkest 5 h, brightest 10 h, Relative Amplitude of light |
| **Light** | Cosinor | Daily mesor, amplitude, acrophase of melanopic EDI |
| **Light** | CPD | Change Point Detection on light exposure pattern |

### AI Analysis Pipeline (fully local)

A 5-agent [LangGraph](https://github.com/langchain-ai/langgraph) pipeline processes the computed metrics:

```
JSON report
    ↓
Agent 1 – Data Summariser        (Ollama LLM)
    ↓
Agent 2 – Keyword Extractor      (Ollama LLM)
              → 3–5 MeSH-style PubMed queries
              → query validated & cleaned (strips artefacts, enforces 2–8 word phrases)
              → if anamnesis present: mixed metric + symptom+metric combo queries
    ↓
Agent 3 – Literature Search      (PubMed E-utilities API — only queries sent)
              → abstracts filtered for relevance by a fast local LLM
    ↓
Agent 4 – Literature Synthesiser (Ollama LLM)
    ↓
Agent 6 – Symptom-Metric Linker  (Ollama LLM) ← only runs when anamnesis provided
              → structured table: symptom → metric Δ → PMID
              → flags unexplained symptoms for further clinical workup
    ↓
Agent 5 – Report Writer          (Ollama LLM, audience-aware)
              → Symptom-Metric Correlation section (when anamnesis present)
              → numbered PubMed reference list (PMID + URL) appended
    ↓
Structured clinical report (expert / doctor / layperson)
```

**Privacy guarantee:** only keyword search queries reach the internet. All raw metrics, identifiers, patient data, and anamnesis remain on the local machine.

### Other Features

- **Multi-period comparison** — side-by-side metric tables with Δ values
- **Anamnesis integration** — Doctor/Expert reports accept a free-text patient anamnesis; symptoms are mapped to metric changes by Agent 6 and persisted per record in the database
- **User authentication** — PBKDF2-HMAC-SHA256 hashed passwords
- **Persistent SQLite storage** — all analyses stored locally in `Actigraph_record.db`
- **JSON report export** — structured reports for downstream analysis
- **AI analysis snapshots** — every LLM report saved to `ai_analyses/` with metadata

---

## Requirements

- Python ≥ 3.10
- [Ollama](https://ollama.com) installed and running locally with at least one model (e.g., `phi4:14b`, `qwen2.5:7b`)
- macOS / Linux (Windows support untested)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/circadian-medicine-suite.git
cd circadian-medicine-suite

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate.bat     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Pull an Ollama model (choose one — larger models give richer reports)
ollama pull phi4:14b             # recommended
# ollama pull qwen2.5:7b         # lighter alternative

# 5. Launch the app
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

Default credentials (change before deployment):
| Username | Password |
|----------|----------|
| user1 | password123 |
| user2 | password456 |

> **Security note:** To add a new user or change passwords, run:
> ```bash
> python -c "from app import _make_entry; import json; print(json.dumps(_make_entry('your_new_password')))"
> ```
> then add the resulting dict to the `USERS` dictionary in `app.py`.

---

## Input Data Format

The application expects one or more CSV files with the following columns:

| Column | Required | Description |
|--------|----------|-------------|
| `DATE/TIME` | ✓ | Timestamp: `MM/DD/YYYY HH:MM:SS` |
| `PIMn` | ✓ | Proportional Integrating Measure (activity count) |
| `MELANOPIC EDI` | ✓ | Melanopic Equivalent Daylight Illuminance (lux) |
| `WHITE LIGHT (LUX)` | ✓ | Photopic illuminance (lux) |
| `SLEEP/WAKE` | ✓ | Binary sleep state (0 = wake, 1 = sleep) |

Sample data files are provided in the `data/` directory.

> ⚠️ **Data privacy:** Never commit real patient data to a public repository. The `.gitignore` excludes CSV files from version control by default.

---

## Usage Workflow

1. **New Analysis** tab — Upload a CSV file, enter a participant ID and description, select a date range, and run the full metric battery.
2. **Previous Analyses** tab — Browse, review, and export stored analyses.
3. **Compare Records** tab — Select two or more record IDs to generate a side-by-side comparison report (JSON).
4. **AI Analysis** tab — Select two record IDs, choose a target audience (expert / doctor / layperson) and Ollama model, then run the pipeline to generate a literature-grounded clinical report. For Doctor and Expert audiences, optionally enter a patient anamnesis — this activates Agent 6, which maps each reported symptom to the most relevant metric change and supporting PubMed evidence, and flags symptoms with no literature match.

---

## Project Structure

```
app.py                  # Main Streamlit application
requirements.txt        # Python dependencies
tools/
    upload_file.py          # File ingestion and date filtering
    database.py             # SQLite ORM (ActigraphDB)
    # Sleep
    sleep_on_off_mid.py         # Sleep onset / offset / mid-sleep detection
    sleep_SRI.py                # Sleep Regularity Index
    sleep_CPD_ms.py             # Circular CPD on mid-sleep phase
    sleep_light_exposure.py     # Light-level classification at sleep/wake transitions
    # Activity
    activity_plotter.py
    activity_IS_IV.py           # Interdaily Stability & Intradaily Variability
    activity_L5_M10_RA.py       # L5, M10, Relative Amplitude
    activity_cosinor.py         # Nonlinear cosinor fitting
    activity_CPD.py             # Activity change-point detection
    # Light
    light_plotter.py
    light_IS_IV.py
    light_L5_M10_RA.py
    light_cosinor.py
    light_CPD.py
    # Reporting & AI
    report_generator.py         # JSON comparison report builder
    llm_conversation.py         # 5/6-agent LangGraph pipeline (+ anamnesis support)
    pubmed_search.py            # PubMed E-utilities wrapper (returns text + PMIDs)
data/                   # Sample actigraphy files (no patient data)
ai_analyses/            # Saved AI report snapshots
```

---

## Citation

If you use this software in your research, please cite:

```
[Author Name] (2026). Circadian Medicine Analysis Suite (Version 1.0) [Computer software].
Charité – Universitätsmedizin Berlin. https://doi.org/10.5281/zenodo.XXXXXXX
```

Or use the `CITATION.cff` file in this repository.

---

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.

---

## License

[MIT License](LICENSE) — © 2026 [Author Name], Charité – Universitätsmedizin Berlin.

---

## Acknowledgements

Developed at the Circadian Medicine Lab, Charité – Universitätsmedizin Berlin.  
Actigraphy data acquired with [device name, e.g., Actiwatch / MotionWatch].  
LLM inference powered by [Ollama](https://ollama.com).  
Literature retrieval via [NCBI PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25499/).
