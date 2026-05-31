# ohdo

[![CI](https://github.com/oddsung/ohdo/actions/workflows/ci.yml/badge.svg)](https://github.com/oddsung/ohdo/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/oddsung/ohdo)

> **AI-native RPA for Windows** — chat with an LLM, get **plain Python** automation code, run it locally. No cloud lock-in.

🇰🇷 **한국어 README**: [README.ko.md](README.ko.md)

---

## What is ohdo?

ohdo turns natural-language requests like *"open Notepad and type hello"* into runnable
[`pywinauto`](https://github.com/pywinauto/pywinauto) / [`pyautogui`](https://pyautogui.readthedocs.io/) /
[Selenium](https://www.selenium.dev/) Python scripts — built **step by step** through a desktop chat UI.
Each step is a card you can edit, re-run, or remove. The output is a self-contained Python project,
not an opaque vendor binding.

## Why ohdo?

| | ohdo | UiPath / Power Automate | Claude Computer Use |
|---|---|---|---|
| **Output** | 🟢 Plain Python (`pywinauto`/Selenium) — git-committable, IDE-editable, portable | 🔴 XAML (vendor lock-in) | 🟡 Per-run vision actions (no reusable artifact) |
| **Cost model** | 🟢 LLM call once per step build, then run forever offline | 🔴 Per-bot/per-user license ($1K–$5K/yr) | 🔴 Vision API cost on every single execution |
| **Determinism** | 🟢 Selector-based code = reproducible | 🟢 Selector-based | 🔴 Different path each run |
| **Offline runtime** | 🟢 No network after build | 🟡 Orchestrator dependent | 🔴 Always-on cloud |
| **Compliance** | 🟢 Local-first (no screen frames leave the machine) | 🟡 Vendor processing | 🔴 Screen content sent to API |
| **Target users** | Developers comfortable reading Python | Citizen developers | Anyone (but pricey + opaque) |

ohdo is **honest about its niche**: a *developer-friendly, code-first* alternative.
If you want a no-code RPA for non-technical users, UiPath/Power Automate is a better fit.
If you want one-shot natural-language automation at any cost, Computer Use is more flexible.
If you want **inspectable, portable, repeatable Python** with a per-step build loop, ohdo is for you.

See [`docs/commercial_review.md`](docs/commercial_review.md) for an honest
competitive analysis (including ohdo's weaknesses).

## Key features

- **Natural language → Python** — request something, see real `pywinauto`/`pyautogui`/Selenium code, edit it, run it
- **Step-card workflow** — every step is a card, cumulatively chained, individually re-runnable
- **Element picker** — click any on-screen widget to auto-generate selector code (auto-routes to desktop UI Automation or Selenium per target)
- **Desktop + browser** — pywinauto (Windows UIA), Selenium (Chrome/Edge), pyautogui (coordinate fallback)
- **Session persistence + import/export** — package a session into a runnable folder (`main.py` + `requirements.txt` + `run.bat`) and ship it to another machine
- **Locally executed** — your screens, prompts, and outputs stay on your machine (only the LLM prompt itself goes to your chosen provider)

> **Heads up**: ohdo is **Windows-only** today (Win32 / UWP / browsers running on Windows).
> Support for macOS / Linux desktops is not on the near-term roadmap.

## Quickstart

### Install (recommended: [`uv`](https://docs.astral.sh/uv/))

```powershell
# Python 3.12+ required. Install uv: pip install uv  (or see uv docs)
uv sync

# ohdo currently uses Gemini CLI as its LLM adapter — install separately:
# https://github.com/google-gemini/gemini-cli
```

`uv sync` reads `pyproject.toml` + `uv.lock` and creates `.venv/` with locked dependencies.

### Install (legacy: `pip`)

```powershell
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Install (Codespaces / Dev Container)

Click the Codespaces badge above, or open the repo in VS Code with the **Dev Containers** extension —
[`.devcontainer/`](.devcontainer/) provisions Python 3.12 + uv + Qt deps + ruff + pre-commit automatically.

> **Note**: Dev containers run on Linux, so the Windows automation libs (`pywinauto`, `pyautogui`, `uiautomation`) cannot execute there.
> The container is for working on `core/` + future `backend/` + `web/`.
> Run the actual Windows automation tests on a local Windows machine (or GitHub Actions `windows-latest`).

### Run

```powershell
.venv\Scripts\python.exe main.py

# Experimental v2 UI:
.venv\Scripts\python.exe main.py --ui v2
```

## Project layout

```
ohdo/
├── main.py                # PySide6 app entry point
├── core/                  # AI engine / workflow / sessions / Windows inspector
├── ui/                    # PySide6 main window + step cards + console
├── ui_v2/                 # UI redesign v2 PoC (separate entry)
├── tests/                 # core / scenarios / ai_integration / GUI suites
├── config/                # settings.json / prompts.json
├── docs/                  # ROADMAP, handoff notes, commercial review, wireframes
├── data/                  # Sessions, captures, logs (git-ignored)
└── legacy_pyqt6/          # Deprecated PyQt6 codebase (run via `uv sync --extra legacy-pyqt6`)
```

Detailed structure: [`CLAUDE.md`](CLAUDE.md) and [`docs/handoff.md`](docs/handoff.md).

## Tests

```powershell
# Core + scenarios (no GUI required)
.venv\Scripts\python.exe -m tests.test_runner --suite core
.venv\Scripts\python.exe -m tests.test_runner --suite scenarios

# AI integration (calls Gemini CLI — costs API tokens, takes ~10–30 s/test)
.venv\Scripts\python.exe -m tests.test_runner --suite ai_integration

# GUI automation (requires a real Windows desktop)
.venv\Scripts\python.exe -m tests.test_runner --suite all
```

Test guide: [`CLAUDE.md`](CLAUDE.md) → "테스트 실행" section.

## Build a Windows installer (desktop_v3)

The Electron desktop (`desktop_v3/`) ships with a **frozen Python bridge** (PyInstaller onedir of
`api_server` + `core`) so it runs on machines without Python installed.

```powershell
# 1. Freeze the bridge (from repo root). pyinstaller is the `build` extra.
uv sync --extra build
uv run --extra build pyinstaller desktop_v3/build/ohdo-bridge.spec --noconfirm   # → dist/ohdo-bridge/

# 2. Stage it for bundling.
Copy-Item dist\ohdo-bridge\* desktop_v3\build\pybridge\ -Recurse -Force

# 3. Build the installer.
cd desktop_v3; npm install; npm run dist            # → release/ohdo-<version>-setup.exe
```

Full runbook, smoke test, and known limitations (code signing, config persistence):
[`docs/BUILD.md`](docs/BUILD.md).

## Roadmap

ohdo is being staged for SaaS expansion under an open-core strategy: Phase 0 (infrastructure standardization) → Phase 1 (storage abstraction + UI–core split) → Phase 2+ (backend / agent / web dashboard).
**Phase 0 + Phase 1 are 100% complete (2026-05-09).** Phase 2 entry is gated on the criteria in [`docs/commercial_review.md`](docs/commercial_review.md).

Full plan: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## License

The desktop client and core libraries are released under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see [`LICENSE`](LICENSE).

**Open-core strategy** ([`docs/ROADMAP.md`](docs/ROADMAP.md) §1):
- **Desktop (this repo)**: AGPL-3.0. Free to use, modify, redistribute. If you offer a modified version as a network service (SaaS), you must release your source under AGPL-3.0 too.
- **Hosted SaaS / Pro features**: planned as separately licensed (closed source). The copyright holder retains the right to dual-license.
- **PySide6 main (LGPL) since 2026-05-12**: the desktop UI now runs on PySide6 (Qt for Python, LGPL — no commercial Qt license needed for redistribution). The previous PyQt6 codebase is preserved at [`legacy_pyqt6/`](legacy_pyqt6/) for reference; install with `uv sync --extra legacy-pyqt6` if you need to run it.

Commercial / non-AGPL licensing inquiries: please open an issue or reach out via the contact details in `pyproject.toml`.

## Contributing

Issues and pull requests are welcome. Coding conventions, test workflow, and the per-step prompt-quality loop are documented in [`CLAUDE.md`](CLAUDE.md). For larger contributions, please open a discussion first so we can align on direction (especially around the open-core boundary).
