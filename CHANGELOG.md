# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
