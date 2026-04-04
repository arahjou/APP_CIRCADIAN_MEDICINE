# Technical Documentation Index

This folder provides developer-facing architecture and implementation documentation for the Circadian Medicine Analysis Suite.

## Documents

- [ARCHITECTURE.md](ARCHITECTURE.md)
  - System topology, component responsibilities, communication pathways
  - End-to-end runtime flow from upload to final outputs
  - Mermaid and ASCII diagrams
- [PYTHON_FILE_MAP.md](PYTHON_FILE_MAP.md)
  - Purpose, inputs, outputs, and interactions for all Python files in the repository
- [TOOLS_AND_SERVICES_API.md](TOOLS_AND_SERVICES_API.md)
  - Public orchestration interfaces and payload contracts used by the app
- [AGENT_PIPELINE.md](AGENT_PIPELINE.md)
  - Full multi-agent pipeline (Agents 1-6), state transitions, and artifacts
- [EXTENSIBILITY_GUIDE.md](EXTENSIBILITY_GUIDE.md)
  - Exact integration path and checklist for adding new modalities (example: skin temperature)
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
  - SQLite schema, relationships, persistence contracts, and artifact ownership

## Recommended Reading Order

1. [ARCHITECTURE.md](ARCHITECTURE.md)
2. [TOOLS_AND_SERVICES_API.md](TOOLS_AND_SERVICES_API.md)
3. [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
4. [AGENT_PIPELINE.md](AGENT_PIPELINE.md)
5. [EXTENSIBILITY_GUIDE.md](EXTENSIBILITY_GUIDE.md)
6. [PYTHON_FILE_MAP.md](PYTHON_FILE_MAP.md)

## Maintenance Rule

When adding or modifying runtime behavior, update:

- [ARCHITECTURE.md](ARCHITECTURE.md) if data flow changed
- [TOOLS_AND_SERVICES_API.md](TOOLS_AND_SERVICES_API.md) if interfaces changed
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) if persistence changed
- [EXTENSIBILITY_GUIDE.md](EXTENSIBILITY_GUIDE.md) if new integration touchpoints were introduced

Last verified against codebase state: 2026-04-04.
