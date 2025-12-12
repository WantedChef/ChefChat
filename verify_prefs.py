from __future__ import annotations

import sys

# Add project root to path
sys.path.insert(0, "/home/chef/chefchat/ChefChat")

from chefchat.interface.tui import TUI_PREFS_FILE, get_saved_layout, save_tui_preference

print(f"Prefs file: {TUI_PREFS_FILE}")

# 1. Test clean state (delete file if exists)
if TUI_PREFS_FILE.exists():
    TUI_PREFS_FILE.unlink()

print(f"Default layout (no file): {get_saved_layout()}")

# 2. Test saving 'kitchen'
print("Saving 'kitchen' preference...")
save_tui_preference("layout", "kitchen")

# Verify file content
print(f"File content: {TUI_PREFS_FILE.read_text()}")
print(f"Loaded layout: {get_saved_layout()}")

# 3. Test saving 'chat'
print("Saving 'chat' preference...")
save_tui_preference("layout", "chat")
print(f"Loaded layout: {get_saved_layout()}")

print("Verification complete.")
