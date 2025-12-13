---
description: Make ChefChat agents fully connected (no more simulations)
---

This workflow implements real logic for the Sommelier (PyPI/Security), Line Cook (Self-healing), and Sous Chef (Planning), replacing current placeholders.

# Phase 1: The Sommelier (Real External Data)

The Sommelier needs to verify packages on PyPI and check for security vulnerabilities.

1.  **Modify `chefchat/kitchen/stations/sommelier.py`**:
    -   Import `aiohttp` and `json`.
    -   Update `_verify_package` to query `https://pypi.org/pypi/{package_name}/json`.
        -   If status 200: Package exists.
        -   Parse JSON to check for "yanked" status or critical info.
    -   Update `_check_security` to run `uv run pip-audit` (or `pip-audit`) if available via `asyncio.create_subprocess_exec`.
        -   If `pip-audit` fails (not installed), fall back to a basic check or warning.

# Phase 2: The Line Cook (Real Intelligence)

The Line Cook needs to actually fix errors using the LLM instead of simulating.

1.  **Modify `chefchat/kitchen/stations/line_cook.py`**:
    -   In `_fix_errors`:
        -   Read the content of the target file (`path` from payload).
        -   Construct a prompt: "Here is code:\n```\n{code}\n```\n\nAnd here are the errors:\n{errors}\n\nFix the code."
        -   Call `self.manager.stream_response` (requires `LineCook` to have access to `KitchenManager`, which it does via `__init__`).
        -   Stream the response (sending updates to TUI).
        -   Save the final fixed code to the file.
    -   Ensure `_fix_errors` uses the same streaming pattern as `_execute_plan` so the user sees progress.

# Phase 3: The Sous Chef (Real Planning)

The Sous Chef should use the LLM to analyze requests instead of pretending to think.

1.  **Modify `chefchat/kitchen/stations/sous_chef.py`**:
    -   Import `KitchenManager` and instantiate it in `__init__` (or pass it in).
    -   In `_process_new_ticket`:
        -   Replace the `asyncio.sleep(0.5)` "Simulate planning" block.
        -   Call `self.manager.generate_plan(request)`.
        -   Send the *real* generated plan to the Line Cook.

# Verification

1.  Run a test that triggers the expediter to fail (e.g., create a file with a syntax error).
2.  Observe the Line Cook attempting to fix it.
3.  Process verify that `_fix_errors` writes new code to the file.
