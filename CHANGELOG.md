# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Research workflow foundation — 2026-10-24

- Added normalized Recording/ImportOptions and explicit CSV column/time settings.
- Optional channels and supplied sleep labels are retained; invalid values remain
  missing, and ambiguous timestamps/duplicates fail with actionable errors.
- Added quality/eligibility policies, reusable numerical service and batch CLI.
- Added optional strict PIM sleep inference without imputation or all-wake fallback.
- Replaced inline numerical orchestration with a shared Streamlit review/run flow.
- Added unique numerical run artifacts, source/input/code hashes, parameters,
  numerical outcomes, and transactional SQLite recording_runs persistence.
- Added single-record HTML/JSON downloads with daily plots and methods, including
  access from Previous Analyses. Existing records remain readable.
- Corrected SRI missing-calendar-day pairing, pair-coverage denominator and DST
  transition handling; sleep bouts retain elapsed duration in minutes.
- Comparison reports now use mean sleep duration, explicit minimum/SD, requested
  record order, optional modality handling and unique strict JSON artifacts.
- Added importer/workflow regressions, CLI and Streamlit tests, explicit local
  Ruff configuration, and updated architecture/API/data-flow documentation.



### Added

- `CONTRIBUTING.md` contribution workflow and quality gates.
- `SUPPORT.md` support and reporting guidance.
- GitHub issue and pull request templates for structured public collaboration.
- Explicit test and CI command documentation in `README.md`.

### Changed

- Updated repository URLs in `README.md`, `paper.md`, and `CITATION.cff` to the public repository path.
- Clarified DOI placeholder handling pending Zenodo archiving.
- Added AI usage disclosure language in `paper.md`.

## [0.1.0] - 2026-04-20

### Added

- Initial public version of Circadian Medicine Analysis Suite with:
  - Streamlit web app for actigraphy upload and analysis
  - Activity, sleep, and melanopic light metric battery
  - Multi-period JSON comparison reports
  - Local multi-agent AI reporting pipeline with PubMed retrieval
  - SQLite persistence and authentication hardening
  - Unit and integration tests plus CI workflow
