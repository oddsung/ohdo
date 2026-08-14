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

## Key features

- **Natural language → Python** — request something, see real `pywinauto`/`pyautogui`/Selenium code, edit it, run it
- **Step-card workflow** — every step is a card, cumulatively chained, individually re-runnable
- **Element picker** — click any on-screen widget to auto-generate selector code (auto-routes to desktop UI Automation or Selenium per target)
- **Desktop + browser** — pywinauto (Windows UIA), Selenium (Chrome/Edge), pyautogui (coordinate fallback)
- **Session persistence + import/export** — package a session into a runnable folder (`main.py` + `requirements.txt` + `run.bat`) and ship it to another machine
- **Locally executed** — your screens, prompts, and outputs stay on your machine (only the LLM prompt itself goes to your chosen provider)

> **Heads up**: ohdo is **Windows-only** today (Win32 / UWP / browsers running on Windows).
> Support for macOS / Linux desktops is not on the near-term roadmap.

## Download (Windows)

**[⬇ Get the latest installer](https://github.com/oddsung/ohdo/releases/latest)** —
`ohdo-<version>-setup.exe`. No Python or Node required; the app bundles its own runtime
and auto-updates via GitHub Releases.

> **Windows SmartScreen**: builds are not code-signed yet, so the first run may warn
> *"Windows protected your PC"*. Click **More info → Run anyway**. Code signing is planned
> once the project has enough users to justify a certificate.

## Run from source (developers)

Two UIs share the same Python `core/`:

- **`desktop_v3/` (Electron + React + TS)** — the shipping product (what the installer packages)
- **`ui_v2/` (PySide6)** — stable fallback UI, kept in maintenance mode

### desktop_v3 (the product)

```powershell
# Python 3.12+ / Node 20+. Install uv: pip install uv  (or see https://docs.astral.sh/uv/)
uv sync                      # Python side (core + api_server bridge) → .venv/
cd desktop_v3
npm install
npm run dev                  # spawns the Python bridge automatically
```

### PySide6 fallback UI

```powershell
uv sync
.venv\Scripts\python.exe main.py --ui v2
```

### AI engine

Pick an engine inside the app (onboarding wizard or Settings): an **OpenAI-compatible API**
(e.g. DeepSeek) or a **CLI AI** adapter. Nothing is hardcoded to a single vendor.

### Codespaces / Dev Container

Click the Codespaces badge above, or open the repo in VS Code with the **Dev Containers**
extension — [`.devcontainer/`](.devcontainer/) provisions Python 3.12 + uv + Qt deps +
ruff + pre-commit automatically.

> **Note**: Dev containers run on Linux, so the Windows automation libs (`pywinauto`,
> `pyautogui`, `uiautomation`) cannot execute there. The container is for working on
> `core/`; run the Windows automation tests on a local Windows machine (or GitHub
> Actions `windows-latest`).

## Project layout

```
ohdo/
├── desktop_v3/            # Electron + React desktop app — the shipping product
├── api_server/            # FastAPI bridge: Electron ↔ core (localhost, token auth)
├── core/                  # AI engine / workflow / sessions / Windows inspector
├── main.py + ui/ + ui_v2/ # PySide6 fallback UI
├── tests/                 # core / scenarios / ai_integration / GUI suites
├── devloop/               # autonomous test-fix harness (Playwright + Electron)
├── config/                # default_settings.json / prompts.json
├── docs/                  # ROADMAP, BUILD runbook, handoff notes
└── data/                  # sessions, captures, logs (git-ignored)
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
**Phase 0 + Phase 1 are 100% complete (2026-05-09).** Phase 2 entry is gated on internal go/no-go criteria (community adoption and user validation).

Full plan: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## License

The desktop client and core libraries are released under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see [`LICENSE`](LICENSE).

**Open-core strategy** ([`docs/ROADMAP.md`](docs/ROADMAP.md) §1):
- **Desktop (this repo)**: AGPL-3.0. Free to use, modify, redistribute. If you offer a modified version as a network service (SaaS), you must release your source under AGPL-3.0 too.
- **Hosted SaaS / Pro features**: developed in a private repository, separately licensed. The copyright holder retains the right to dual-license.
- **Long-term pricing direction**: **free for individuals**; businesses and commercial services will be offered a commercial license and paid Pro/cloud features.
- **PySide6 (LGPL) since 2026-05-12**: the fallback UI runs on PySide6 (Qt for Python, LGPL — no commercial Qt license needed for redistribution). The earlier PyQt6 codebase was removed from the public tree and is kept in git history only.

Commercial / non-AGPL licensing inquiries: please open an issue or reach out via the contact details in `pyproject.toml`.

## Contributing

Issues and pull requests are welcome. Coding conventions, test workflow, and the per-step prompt-quality loop are documented in [`CLAUDE.md`](CLAUDE.md). For larger contributions, please open a discussion first so we can align on direction (especially around the open-core boundary).
