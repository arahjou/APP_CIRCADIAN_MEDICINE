# Release Checklist: v0.1.2 (stable, non-prerelease)

Use this checklist when creating the GitHub release for `v0.1.2`.

- [ ] Confirm branch is `main` and up to date with `origin/main`.
- [ ] Confirm CI is green on the release commit (`ruff`, `mypy`, and `pytest` workflows pass).
- [ ] Verify `README.md`, `CITATION.cff`, and `paper.md` contain DOI `10.5281/zenodo.19669862`.
- [ ] Verify `CITATION.cff` author metadata is correct:
  - [ ] `given-names: Ali`
  - [ ] `family-names: Rahjouei`
  - [ ] `name-suffix: Dr. rer. nat.`
  - [ ] `orcid: https://orcid.org/0000-0003-3973-6333`
- [ ] Verify root `LICENSE` file exists and is MIT.
- [ ] Create and push tag:
  - [ ] `git tag v0.1.2`
  - [ ] `git push origin v0.1.2`
- [ ] Create GitHub Release from tag `v0.1.2`:
  - [ ] Title: `v0.1.2`
  - [ ] Mark as latest release
  - [ ] **Do not** mark as prerelease
- [ ] Paste release notes (template below) into the release description.
- [ ] In Zenodo, confirm the new GitHub release was archived and minted a new version DOI.
- [ ] Update `README.md` and `CITATION.cff` with the final Zenodo DOI for `v0.1.2` if it changed.
- [ ] Verify GitHub repository page shows a published release (not prerelease).

## Release notes template (GitHub)

### Circadian Medicine Analysis Suite v0.1.2

This stable release focuses on type safety improvements and CI reliability.

#### Added
- Type stub packages for better type checking (`pandas-stubs`, `types-plotly`, `scipy-stubs`).
- `ActigraphDBLike` protocol for improved duck-typing compatibility in tests.
- Comprehensive type annotations across codebase.

#### Changed
- Fixed all mypy type checking errors in core modules:
  - `tools/sleep_algos.py`: Proper type annotations for numpy arrays and return types.
  - `tools/llm_conversation.py`: Runtime type checking for union types.
  - `app.py`: Protocol-based typing for database-like objects.
  - `tests/unit/test_dashboard_helpers.py`: Explicit return type annotations.
- Updated CI workflow requirements to include type stub packages.

#### Fixed
- GitHub Actions CI mypy type checking now passes without errors.
- Resolved 45 type errors across 22 files.

#### Verification
- `ruff check app.py tools services scripts tests`
- `mypy tools/settings.py tools/pubmed_search.py services tests/unit tests/integration`
- `pytest -q tests`
