from __future__ import annotations

import time

print("Phase 1: Basic Imports")
t0 = time.time()
print(f"Basic imports took: {time.time() - t0:.4f}s")

print("Phase 2: Textual Imports")
t0 = time.time()
print(f"Textual imports took: {time.time() - t0:.4f}s")

print("Phase 3: ChefChat Config")
t0 = time.time()
print(f"Config import took: {time.time() - t0:.4f}s")

print("Phase 4: ChefChat Interface")
t0 = time.time()
print(f"Interface import took: {time.time() - t0:.4f}s")

print("Phase 5: ChefChat Entrypoint")
t0 = time.time()
print(f"Entrypoint import took: {time.time() - t0:.4f}s")

print("Done.")
