
import sys
import os

print("DEBUG: Starting debug_import.py", flush=True)

try:
    print("DEBUG: Importing chefchat.interface.tui module...", flush=True)
    import chefchat.interface.tui
    print(f"DEBUG: Module imported. File: {chefchat.interface.tui.__file__}", flush=True)
except Exception as e:
    print(f"ERROR: Failed to import module: {e}", flush=True)
    sys.exit(1)

try:
    print("DEBUG: Importing 'run' from chefchat.interface.tui...", flush=True)
    from chefchat.interface.tui import run
    print("DEBUG: 'run' imported successfully.", flush=True)
except Exception as e:
    print(f"ERROR: Failed to import 'run': {e}", flush=True)
    sys.exit(1)

print("DEBUG: Calling run(verbose=True)...", flush=True)
try:
    run(verbose=True)
    print("DEBUG: run() returned.", flush=True)
except Exception as e:
    print(f"ERROR: run() failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
