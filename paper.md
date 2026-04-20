---
title: 'Circadian Medicine Analysis Suite: A Privacy-Preserving Web Application for Actigraphy-Based Circadian Analysis with AI-Augmented Clinical Reporting'
tags:
  - Python
  - circadian medicine
  - actigraphy
  - sleep analysis
  - large language models
  - clinical decision support
authors:
  - name: "Ali Rahjouei"
    orcid: 0000-0003-3973-6333
    affiliation: 1
affiliations:
  - name: Charité – Universitätsmedizin Berlin, Department of Anesthesiology and Intensive Care Medicine | CCM | CVK, Circadian Medicine Group, Berlin, Germany
    index: 1
date: 23 March 2026
bibliography: paper.bib
---

# Summary

Wrist actigraphy is a widely used ambulatory method for assessing sleep-wake patterns and circadian rhythm disturbances in clinical and research settings [@Smith2018]. However, translating raw actigraphy recordings into clinically interpretable circadian profiles typically requires combining multiple analytical approaches — including nonparametric rest-activity analysis, cosinor modelling, and sleep-wake scoring — together with the expertise needed to contextualise those metrics against the biomedical literature.

**Circadian Medicine Analysis Suite** is an open-source Python/Streamlit web application that addresses this gap. It provides a unified, browser-based interface for uploading actigraphy data, computing a broad battery of established circadian metrics, comparing recordings across time periods, and generating structured clinical reports grounded in automatically retrieved PubMed literature, while keeping raw patient data, identifiers, and computed metrics on the local machine. Only de-identified literature-search queries and PubMed retrieval requests are sent to external services.

# Statement of need

Clinician-researchers working with wrist actigraphy need reproducible analysis pipelines that connect raw recordings to interpretable circadian and sleep metrics without exposing patient-level data to external services. In many teams, this process is still fragmented across multiple scripts or tools, which increases manual handoffs and makes longitudinal comparison harder to standardize.

Circadian Medicine Analysis Suite addresses this need by providing one local workflow for ingesting actigraphy exports, computing nonparametric and model-based rhythm metrics, comparing recording periods, and generating literature-grounded narrative reports. The target users are clinician-researchers, postdoctoral scientists, and translational chronobiology teams that require privacy-preserving analysis with auditable outputs.

# State of the field

Commonly used actigraphy tools such as Actiware (Philips Respironics), GGIR [@Migueles2019], pyActigraphy [@Hammad2021], and nparACT [@Blume2016] provide important functionality, but typically emphasize specific parts of the workflow. In routine translational practice, teams often still need to assemble multiple tools to cover activity metrics, sleep metrics, light exposure, longitudinal comparison, and report generation.

This project was built instead of extending one existing package because the required contribution is cross-cutting: unified handling of activity, sleep, and melanopic light channels, integrated period-to-period delta reporting, and a local AI-supported evidence-synthesis pipeline constrained to de-identified PubMed queries. The scholarly contribution is the end-to-end, privacy-preserving integration of these components for circadian medicine use cases.

# Software design

The architecture prioritizes three design constraints: (1) local-first data handling for privacy-sensitive settings, (2) reproducible metric computation across repeated analyses, and (3) clinician-facing usability through a single web interface.

## Input data and storage

The application ingests minute-resolution wrist actigraphy CSV files exported from compatible devices. Required columns are: `DATE/TIME`, `PIMn` (device-exported activity counts), `MELANOPIC EDI` (melanopic equivalent daylight illuminance, lux [@CIE2018; @Lucas2014]), `WHITE LIGHT (LUX)`, and `SLEEP/WAKE`. Data are stored in a local SQLite database (`Actigraph_record.db`) keyed by user-defined participant IDs and recording periods.

## Circadian and sleep metric engine

All metrics are computed in Python using `numpy`, `scipy`, and `pandas`.

**Activity domain:**

- *Interdaily Stability (IS) and Intradaily Variability (IV)* — nonparametric measures of day-to-day rhythm consistency and within-day fragmentation, computed over rolling 2-day windows [@VanSomeren1999].
- *L5, M10, Relative Amplitude (RA)* — the least-active 5-hour period, most-active 10-hour period, and their relative amplitude, anchored to clock noon [@VanSomeren1999].
- *Cosinor analysis* — daily nonlinear least-squares fitting of the cosine function $y = M + A \cos\!\left(\frac{2\pi t}{24} - \phi\right)$ to yield mesor ($M$), amplitude ($A$), and acrophase ($\phi$) per recording day [@Refinetti2007].
- *Composite phase deviation (CPD)* — identification of abrupt shifts in the phase of the rhythm [@Fischer2016].

**Sleep domain:**

- *Sleep onset, offset, and mid-sleep time* — extracted from the `SLEEP/WAKE` time series, with gap-filling for brief within-sleep awakenings.
- *Sleep Regularity Index (SRI)* — the probability that sleep-wake state at time $t$ on one day matches state at the same time on the next, averaged over all day pairs in a sliding window [@Phillips2017].
- *Circular CPD on mid-sleep phase* — application of circular statistics to detect shifts in the timing of the mid-sleep point, using noon-centred angles and a combined mean-deviation/day-to-day-deviation score, conceptually related to composite phase deviation [@Fischer2016].
- *Sleep-light exposure* — categorical analysis of melanopic EDI levels during three-hour windows around primary sleep onset and offset events.

**Light domain:**

An equivalent suite (IS, IV, L5, M10, RA, cosinor, CPD) is computed on the melanopic EDI channel, enabling direct comparison of photic input rhythmicity with activity rhythmicity.

## Longitudinal comparison outputs

Users can select any two database records and generate a structured JSON comparison report listing each metric by domain alongside the inter-period difference ($\Delta$). This supports within-subject longitudinal designs (for example, baseline versus intervention) and between-condition comparisons.

## AI-supported reporting pipeline

A locally executed 5-agent pipeline, with an optional sixth symptom-metric linker, is implemented with LangGraph [@LangGraphSoftware] and Ollama [@OllamaSoftware]:

| Agent | Role | Implementation |
|-------|------|----------------|
| 1 — Data Summariser | Condenses the metric table into a clinical narrative (~400 words) | Local Ollama LLM |
| 2 — Keyword Extractor | Generates PubMed search queries; validates and cleans output; when anamnesis is present, generates a mixed set of 3 metric-focused and 2 symptom-plus-metric queries | Local Ollama LLM |
| 3 — Evidence Retriever | Retrieves abstracts via NCBI PubMed E-utilities and filters out off-topic results with a fast local LLM relevance pass | NCBI E-utilities + Local Ollama LLM |
| 4 — Literature Synthesiser | Links retrieved evidence to individual metric findings | Local Ollama LLM |
| 5 — Report Writer | Produces a structured narrative in the chosen register; includes a "Symptom-Metric Correlation" section when Agent 6 is active; concludes with a numbered PubMed reference list | Local Ollama LLM |
| 6 — Symptom-Metric Linker *(optional)* | When a patient anamnesis is provided for Doctor or Expert output, maps each reported symptom to the most relevant metric change ($\Delta$) and supporting PubMed abstract; explicitly flags symptoms with no literature match for further workup | Local Ollama LLM |

The pipeline supports three audience registers: *expert* (full chronobiology terminology), *doctor* (clinical language), and *layperson* (plain language). For the Doctor and Expert registers, clinicians can optionally enter free-text anamnesis, activating Agent 6 as a conditional LangGraph node. Symptoms lacking supporting literature are explicitly flagged for further workup.

Only de-identified literature-search queries and PubMed retrieval requests leave the local machine; raw actigraphy, computed metrics, participant identifiers, and full anamnesis text remain local. Literature retrieval uses the NCBI Entrez E-utilities API [@NCBIEutilities]. Reports are saved to disk in both plain text and structured JSON with provenance metadata.

## Authentication and security

Multi-user access is controlled via PBKDF2-HMAC-SHA256 password hashing with a per-user random 16-byte salt and constant-time comparison. Passwords are never stored in plaintext.

# Research impact statement

The software is currently used in internal Circadian Medicine Lab workflows at Charité for standardized metric extraction and longitudinal comparison from actigraphy exports. In this setting, the suite replaces multi-tool manual analysis steps with one version-controlled pipeline and persistent JSON outputs, improving reproducibility and reducing interpretation handoff time across collaborators.

The project is openly released under MIT, includes automated tests, and provides executable examples and documentation to support external reuse. The combination of local-first privacy constraints, cross-domain circadian metrics, and literature-linked reporting is intended to make the tool directly reusable in similar translational chronobiology and sleep-medicine research environments.

# AI usage disclosure

Generative AI models are part of the software runtime pipeline described in this paper (local Ollama-backed agents for summarization and literature synthesis). These model outputs are treated as software-generated artifacts and are not used as standalone evidence for scientific claims without human verification.

# Availability

The software is available at [https://github.com/arahjou/APP_CIRCADIAN_MEDICINE](https://github.com/arahjou/APP_CIRCADIAN_MEDICINE) under the MIT License. It requires Python \>= 3.10, a local Ollama installation, and a standard research workstation. A complete installation guide and sample anonymized data are provided in the repository.

# Acknowledgements

Developed at the Circadian Medicine Lab, Charité – Universitätsmedizin Berlin. The author thanks Luísa Klaus Pilz for scientific guidance. LLM inference uses Ollama [@OllamaSoftware]; literature retrieval uses the NCBI Entrez E-utilities API [@NCBIEutilities].

# References
