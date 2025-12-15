# Repository Guidelines

## Project Structure & Module Organization
- `chefchat/` — core application code (agents, LLM backends, tools, UI, bots); most changes land here.
- `tests/` — pytest suites covering core logic, tools, onboarding, and bot helpers.
- `docs/` — reference docs and onboarding notes; keep README in sync with notable behavior changes.
- `scripts/` — utility scripts for local workflows (formatting, releasing, CI helpers).
- Config lives under `~/.chefchat/` (or `CHEFCHAT_HOME`) with legacy `.vibe` fallback; use `chefchat/core/config.py` helpers for paths.

## Build, Test, and Development Commands
- `uv run pytest` — run the test suite; prefer targeted paths (e.g., `tests/core`, `tests/tools`).
- `uv run ruff check .` — lint Python files.
- `uv run python -m chefchat` — start the CLI/TUI locally.
- `uv run python -m chefchat.bots.telegram.telegram_bot` — run the Telegram bot (requires `TELEGRAM_BOT_TOKEN`).
- `uv run python -m chefchat.bots.telegram.mini_app.control up` — manage the Telegram mini-app service.

## Coding Style & Naming Conventions
- Python 3.11+, type hints required; keep functions small and pure where practical.
- Follow existing patterns in each module; prefer dependency injection over globals.
- Use `ruff` autofixes sparingly; avoid unnecessary reformatting of untouched code.
- Names: modules and files use `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE_CASE`.

## Testing Guidelines
- Add or update pytest coverage alongside behavior changes; use fixtures where available.
- Name tests `test_<behavior>()` and place near related modules (e.g., `tests/tools/test_grep.py` for tool changes).
- For bot changes, mock network/services; avoid hitting external APIs in tests.
- Keep fast unit tests default; gate slow/integration tests with markers.

## Commit & Pull Request Guidelines
- Commit messages: concise, imperative (e.g., “Add Telegram CLI diagnostics”); group related changes per commit.
- Pull requests should describe intent, major changes, risks, and manual testing. Link issues/tickets when available.
- Include screenshots or terminal snippets for UX changes (TUI/bot menus).
- Note configuration migrations (e.g., `.chefchat` vs `.vibe`) in PR descriptions.

## Security & Configuration Tips
- Never log secrets; use redaction utilities in `core/utils` and CLI provider sanitizers.
- Prefer `~/.chefchat/.env` for local secrets; keep `.chefchatignore`/`.vibeignore` updated to exclude sensitive paths.
- Review new external commands with `GitCommandValidator`/`SecureCommandExecutor` patterns before exposing in bots.
