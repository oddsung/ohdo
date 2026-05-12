# Contributing to ohdo

Thanks for your interest. ohdo is a small project with a focused scope, so a few notes up front will save us all time.

🇰🇷 **한국어 버전**: [CONTRIBUTING.ko.md](CONTRIBUTING.ko.md)

---

## Before you open a PR

1. **Open a discussion or issue first** for anything beyond a small fix or typo. ohdo follows an open-core strategy (see [`COMMERCIAL.md`](COMMERCIAL.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md) §1) and we want to make sure your idea fits the planned direction *before* you spend time coding.
2. **Read the relevant doc** — depending on the area:
   - Project layout & test workflow: [`CLAUDE.md`](CLAUDE.md)
   - Long-term roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)
   - Recent change history & open work: [`docs/handoff.md`](docs/handoff.md)
   - Honest competitive analysis: [`docs/commercial_review.md`](docs/commercial_review.md)
3. **Check existing tests** — `tests/test_runner.py` orchestrates `core` / `scenarios` / `ai_integration` / GUI suites. Most contributions need a regression test in `core` or `scenarios`.

## Development setup

```powershell
# Recommended: uv (https://docs.astral.sh/uv/)
uv sync --extra dev
.venv\Scripts\python.exe -m pre_commit install

# Run lint + format checks
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .

# Run the no-GUI test suites locally
venv\Scripts\python.exe -m tests.test_runner --suite core
venv\Scripts\python.exe -m tests.test_runner --suite scenarios
```

CI runs lint + ubuntu/windows test suites on every push and PR (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Coding conventions

- **Python 3.12+**. Type hints encouraged but not yet enforced repo-wide (mypy is on the roadmap, gated behind Phase 1 type-hint work).
- **`ruff` is the source of truth** for lint and format. Run `ruff format` before committing; pre-commit will enforce it anyway.
- **No `em-dash` in test/log/print messages** — Windows `cp949` console encoding can't handle it. Use a hyphen. (Markdown / docstrings are fine.)
- **One `from core.app_service import …`** in any `ui/` file — direct imports of `core.session_manager`, `core.ai_engine`, `core.execution_kernel`, `core.workflow_engine`, `core.import_manager`, `core.prompt_builder`, `core.win_inspector`, or `core.storage.*` are blocked by tests `test_80` / `test_84` / `test_85`.
- **`legacy_pyqt6/` is frozen** — the previous PyQt6 codebase is preserved for reference only since 2026-05-12 (PySide6 main switch). Do not mirror new changes there.

## Sign your commits (DCO)

ohdo uses the [Developer Certificate of Origin](https://developercertificate.org/) ("DCO") instead of a heavyweight CLA. Every commit must carry a `Signed-off-by:` line — this is a single declaration that you wrote the patch (or have the right to submit it) and that you agree to license it under AGPL-3.0.

The easiest way is `git commit -s`:

```bash
git commit -s -m "Fix the thing"
# adds "Signed-off-by: Your Name <your.email@example.com>" automatically
```

Configure your signature once with `git config user.name "Your Name"` and `git config user.email "your.email@example.com"`.

For larger / structural contributions we may ask you to also sign a per-contribution **CLA** so the project can dual-license under [`COMMERCIAL.md`](COMMERCIAL.md) without re-collecting permissions. We try to keep this rare — most one-file patches will not need it.

## Pull request checklist

- [ ] Linked issue / discussion exists (for non-trivial changes).
- [ ] `ruff check .` and `ruff format --check .` pass locally.
- [ ] `tests/test_runner.py --suite core` and `--suite scenarios` pass locally.
- [ ] New behavior has a regression test in `tests/test_core.py` or `tests/test_scenarios.py`.
- [ ] Every commit has a `Signed-off-by:` line.
- [ ] PR description explains the *why*, not just the *what*.

## Areas where we especially welcome contributions

- **i18n** — ohdo's user-facing strings are still partly Korean-only. Cleaning these up into a proper i18n layer is high-value and not tied to a deep understanding of the rest of the codebase.
- **Element picker robustness** — edge cases around UWP apps, hidden control types, browser frames.
- **Test fixtures** — more `core` / `scenarios` cases pinning down behavior we currently rely on by inspection.
- **Documentation** — especially English versions of internal Korean docs.

## What's out of scope (for now)

- macOS / Linux desktop support (Windows-only is a deliberate niche choice — see `docs/commercial_review.md`).
- Vendor-locked formats (XAML, proprietary scripting). The whole point of ohdo is plain Python.
- Phase 2 SaaS code — that lives behind the open-core boundary and is not yet open.

## Thanks

Even reading this far helps. If something is unclear, open an issue and we'll improve the docs.
