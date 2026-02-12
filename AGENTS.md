# AGENTS Guide for Gold-Fund-monitor

This file is for coding agents working in this repository.
Follow these repository-specific conventions first, then general best practices.

## 1) Project Snapshot

- Stack: Python 3.8+, Flask backend, Vue 3 (Options API) + Tailwind frontend.
- Runtime entrypoint: `app.py`; app factory is `create_app()` in `app/__init__.py`.
- Main domains:
  - Gold real-time quote monitoring (multi-source failover).
  - Fund valuation, holdings management, portfolio contribution estimation.
- Persistence: local JSON file at `data/data.json` with atomic writes.
- Concurrency:
  - Background daemon thread for gold fetching.
  - `ThreadPoolExecutor` for concurrent fund/holdings fetch.
  - Global `threading.RLock` in `app/models/state.py` for shared mutable state.

## 2) Repository Structure

- `app.py`: startup + background thread boot.
- `app/config.py`: global constants, paths, API endpoints, cache/interval settings.
- `app/models/state.py`: all in-memory shared state + lock.
- `app/routes/*.py`: Flask Blueprint API endpoints.
- `app/services/*.py`: business logic and data fetch/persistence services.
- `templates/index.html`: full frontend UI + Vue app + CSS.
- `config/launcher.ini`: optional Python interpreter override (`start.bat` reads it).
- `data/data.json`: persisted runtime data.

## 3) Build / Run / Lint / Test Commands

Run from repo root: `D:\Desktop\Gold-Fund-monitor`.

### Environment setup

- Create venv (Windows): `python -m venv venv`
- Activate (PowerShell): `venv\Scripts\Activate.ps1`
- Install deps: `pip install -r requirements.txt`

### Run

- Direct run: `python app.py`
- Launcher (Windows): `start.bat`

### Build / sanity checks

- Syntax/build sanity (recommended baseline): `python -m compileall app.py app`
- Optional import smoke check: `python -c "from app import create_app; create_app(); print('ok')"`

### Lint / formatting

No pinned lint/format config files were found (`pyproject.toml`, `.flake8`, etc.).

- Baseline (no extra deps): `python -m compileall app.py app`
- If tools are installed, recommended:
  - Lint: `ruff check .`
  - Format: `ruff format .`

### Tests

There is currently no committed `tests/` suite.

If/when tests are added, use:

- Run all tests: `pytest -q`
- Run one file: `pytest tests/test_fund_fetcher.py -q`
- Run one test function (single test):
  - `pytest tests/test_fund_fetcher.py::test_fetch_fund_data_success -q`
- Run by keyword: `pytest -k "holdings and cache" -q`

If using `unittest` style later, single-test equivalent:

- `python -m unittest tests.test_fund_fetcher.TestFundFetcher.test_fetch_fund_data_success`

## 4) API and Runtime Expectations

- Keep API responses in consistent JSON shape:
  - Success: `{"success": True, ...}`
  - Failure: `{"success": False, "message": "..."}`
- Do not surface raw exceptions to clients for expected external-data failures.
- External HTTP sources are unreliable; degrade gracefully.
- Preserve current semantics where fetch failures return `None` and caller handles fallback.

## 5) Python Style Guidelines

### Encoding and docs

- Keep `# -*- coding: utf-8 -*-` at top of Python modules (current repo convention).
- Prefer concise module/function docstrings; Chinese docs/comments are common in this repo.
- Add comments only for non-obvious logic (fallbacks, cache, parsing, lock-sensitive code).

### Imports

- Use 3 groups with blank lines:
  1. Standard library
  2. Third-party
  3. Local app imports (`from app...`)
- Avoid unused imports; avoid wildcard imports.

### Formatting and structure

- Follow PEP 8 defaults and 4-space indentation.
- Keep route handlers thin; put business logic in `app/services/*`.
- Keep constants in `app/config.py`, not inline magic values in multiple files.

### Types

- Existing code is mostly untyped; keep edits consistent with local file style.
- Type hints are welcome for new complex functions, but avoid partial/inconsistent noise.

### Naming

- Python variables/functions: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Blueprint variables: `<domain>_bp`.
- Boolean flags: clear predicates (`is_*`, `has_*`, etc.).

### Error handling

- Wrap external I/O (HTTP, file write, JSON parse, thread workers) in `try/except`.
- On exception: log context, return safe fallback (`None`, stale cache, or failure JSON), keep process alive.
- Avoid broad `except` blocks without explicit fallback behavior.

### State and concurrency

- Guard shared globals from `app/models/state.py` with `with lock:`.
- Avoid long blocking operations while holding `lock`.
- Prefer: copy minimal state under lock, compute outside lock, then write back under lock.
- Keep background helper threads daemonized (`daemon=True`).

### Persistence

- Use `save_data()` for persistence; do not write `data/data.json` directly.
- Preserve atomic write behavior (`.tmp` + `fsync` + `os.replace`).
- Keep backward compatibility of keys:
  - `manual_records`, `price_history`, `alert_settings`
  - `fund_watchlist`, `fund_holdings`, `fund_portfolios`

## 6) Frontend Guidelines (`templates/index.html`)

- Keep Vue style as Options API (`data`, `computed`, `methods`, `watch`, `mounted`).
- Use `camelCase` for JS identifiers/methods.
- Keep `fetch` + JSON handling pattern with `if (data.success)` checks.
- Ensure polling timers are cleaned/reset when switching views.
- Preserve existing UI language: dark premium theme, rich animation, Tailwind utilities.
- Do not introduce a new frontend build system unless explicitly requested.

## 7) Architecture and Layering Rules

- Routes (`app/routes`) should mainly validate input, call service, return JSON.
- Services (`app/services`) own fetching/parsing/caching/business logic.
- Shared mutable runtime state belongs only in `app/models/state.py`.
- Global config values belong in `app/config.py`.

## 8) Cursor / Copilot Rules Discovery

Checked locations:

- `.cursorrules`
- `.cursor/rules/`
- `.github/copilot-instructions.md`

Status: no Cursor/Copilot instruction files were found when generating this guide.

If such files are added later, merge their directives into this file and treat the more specific scope rule as higher priority.

## 9) Agent Pre-merge Checklist

- Run at least: `python -m compileall app.py app`
- If API behavior changed, manually sanity-check related endpoints.
- If polling/cache/lock logic changed, verify race/regression risk paths.
- Keep changes minimal and consistent with existing Chinese-facing UX text.
- Update this guide when introducing new tools, commands, or architecture conventions.
