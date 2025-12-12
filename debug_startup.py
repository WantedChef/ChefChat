from __future__ import annotations

import os
import sys
import traceback

from rich import print

print("[bold yellow]DEBUG: Starting debug script (Interactive)[/]")

try:
    # Force minimal env
    os.environ["FORCE_COLOR"] = "1"
    os.environ["TERM"] = "xterm-256color"

    # Try import
    print("DEBUG: Importing ChefChatApp...")
    from chefchat.interface.tui import ChefChatApp

    print("DEBUG: Import successful.")

    # Instantiate
    print("DEBUG: Instantiating App...")
    app = ChefChatApp()
    print("DEBUG: App instantiated.")

    # Run Interactive
    print("DEBUG: Starting App (Interactive)...")
    app.run()
    print("DEBUG: App finished successfully.")

except Exception:
    print("[bold red]FATAL: Exception caught[/]")
    traceback.print_exc()
    sys.exit(1)
