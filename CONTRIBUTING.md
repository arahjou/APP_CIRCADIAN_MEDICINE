# Contributing

Thank you for your interest in improving Circadian Medicine Analysis Suite.

## How to contribute

1. Open a GitHub issue describing the bug, enhancement, or question.
2. Fork the repository and create a focused branch from `main`.
3. Keep changes scoped to one topic per pull request.
4. Add or update tests when behavior changes.
5. Run local checks before opening a pull request.
6. Open a pull request that references the related issue.

## Local checks

```bash
pytest -q tests
ruff check app.py tools services scripts tests
mypy tools/settings.py tools/pubmed_search.py services tests/unit tests/integration
```

## Pull request expectations

- Use clear commit messages.
- Describe what changed and why.
- Include reproduction and validation steps for bug fixes.
- Update documentation (`README.md`, `docs/`, and `paper.md` when relevant).

## Scope

High-priority contributions include:

- Actigraphy metric correctness and validation
- Test coverage and CI reliability
- Documentation quality and reproducibility improvements
- Security hardening and privacy-preserving defaults
