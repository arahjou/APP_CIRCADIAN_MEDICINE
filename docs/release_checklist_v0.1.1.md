# Release Checklist: v0.1.1 (stable, non-prerelease)

Use this checklist when creating the GitHub release for `v0.1.1`.

- [ ] Confirm branch is `main` and up to date with `origin/main`.
- [ ] Confirm CI is green on the release commit (`ruff` and `pytest` workflows pass).
- [ ] Verify `README.md`, `CITATION.cff`, and `paper.md` contain DOI `10.5281/zenodo.19669862`.
- [ ] Verify `CITATION.cff` author metadata is correct:
  - [ ] `given-names: Ali`
  - [ ] `family-names: Rahjouei`
  - [ ] `name-suffix: Dr. rer. nat.`
  - [ ] `orcid: https://orcid.org/0000-0003-3973-6333`
- [ ] Verify root `LICENSE` file exists and is MIT.
- [ ] Create and push tag:
  - [ ] `git tag v0.1.1`
  - [ ] `git push origin v0.1.1`
- [ ] Create GitHub Release from tag `v0.1.1`:
  - [ ] Title: `v0.1.1`
  - [ ] Mark as latest release
  - [ ] **Do not** mark as prerelease
- [ ] Paste release notes (template below) into the release description.
- [ ] In Zenodo, confirm the new GitHub release was archived and minted a new version DOI.
- [ ] Update `README.md` and `CITATION.cff` with the final Zenodo DOI for `v0.1.1` if it changed.
- [ ] Verify GitHub repository page shows a published release (not prerelease).

## Release notes template (GitHub)

### Circadian Medicine Analysis Suite v0.1.1

This stable release focuses on publication-readiness and CI reliability.

#### Added
- MIT `LICENSE` file at repository root.
- JOSS-aligned paper structure with required headings:
  - Summary
  - Statement of need
  - State of the field
  - Software design
  - Research impact statement
  - AI usage disclosure

#### Changed
- Documentation and citation metadata refined for JOSS submission readiness.
- Lint and test compliance updates to keep CI checks green.

#### Verification
- `ruff check app.py tools services scripts tests`
- `pytest -q tests`
