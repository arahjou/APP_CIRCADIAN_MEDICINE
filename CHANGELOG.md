# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository setup for publication

## [1.2.0] - 2025-10-21

### Added
- Conversational AI feature for follow-up questions
- Chat interface in AI Analysis tab
- Context-aware responses with conversation history
- Psychology and behavioral impact analysis

### Changed
- Enhanced AI prompts for better clinical insights
- Improved session state management for chat

## [1.1.0] - 2025-10-08

### Added
- AI-powered analysis using Ollama LLM
- Model selection (phi4:14b, llama3.2, gemma3:12b, qwen3:8b)
- Clinical interpretation of circadian metrics
- JSON report generation
- Download options for analysis results

### Changed
- Updated tab structure (3 tabs instead of 2)
- Enhanced comparison report with JSON output

### Documentation
- Added AI_ANALYSIS_IMPLEMENTATION.md
- Added AI_ANALYSIS_SETUP.md

## [1.0.0] - 2025-10-XX

### Added
- Initial release with core functionality
- Streamlit-based web interface
- File upload and data processing
- Sleep analysis metrics:
  - Sleep light exposure
  - Sleep onset/offset/midpoint
  - CPD (Circadian Phase Dispersion)
  - SRI (Sleep Regularity Index)
- Activity analysis metrics:
  - IS (Interdaily Stability)
  - IV (Intradaily Variability)
  - L5/M10/RA (Activity rhythm metrics)
  - Cosinor fitting
  - CPD for activity
- Light analysis metrics:
  - Melanopic EDI analysis
  - IS/IV for light
  - L5/M10/RA for light
  - Cosinor fitting for light
- SQLite database for record storage
- Comparison reports between two periods
- HTML report generation

### Database
- Analysis records table
- Sleep analysis storage
- Activity analysis storage
- Light analysis storage

## [0.1.0] - Early Development

### Added
- Basic project structure
- Core analysis functions
- Data visualization tools
- Database schema design

---

## Types of Changes
- `Added` for new features
- `Changed` for changes in existing functionality
- `Deprecated` for soon-to-be removed features
- `Removed` for now removed features
- `Fixed` for any bug fixes
- `Security` for vulnerability fixes
