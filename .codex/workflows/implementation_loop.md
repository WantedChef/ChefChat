# Workflow: The Implementation Loop (Cooking the Dish)

This workflow defines how to safely implement a feature or fix a bug.

## 1. Mise en Place (Preparation)
-   [ ] **Read Context**: Analyze the files involved (`read_file`).
-   [ ] **Check Standards**: Verify current linting rules (`.pre-commit-config.yaml`, `pyproject.toml`).
-   [ ] **Verify State**: Run existing tests (`pytest`) to ensure a clean starting point.

## 2. Cooking (Implementation)
-   [ ] **Plan Edits**: Identify the exact lines to change.
-   [ ] **Atomic Writes**: Use `replace` for small edits or `write_file` for new files.
-   [ ] **Refactor**: Apply changes idiomatically (Python 3.12+ style).

## 3. Tasting (Verification)
-   [ ] **Lint**: Run `ruff check .` to catch style errors immediately.
-   [ ] **Type Check**: Run `pyright` (or `mypy`) to ensure type safety.
-   [ ] **Test**: Run `pytest <modified_file>` to verify functionality.

## 4. Plating (Finalization)
-   [ ] **Clean Up**: Remove temporary files or debug prints.
-   [ ] **Commit**: Create a concise commit message describing the *why* and *what*.
