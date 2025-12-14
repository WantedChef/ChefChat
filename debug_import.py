import time
import sys

print("Phase 1: Basic Imports")
t0 = time.time()
import asyncio
import os
print(f"Basic imports took: {time.time() - t0:.4f}s")

print("Phase 2: Textual Imports")
t0 = time.time()
from textual.app import App
print(f"Textual imports took: {time.time() - t0:.4f}s")

print("Phase 3: ChefChat Config")
t0 = time.time()
from chefchat.core.config import VibeConfig
print(f"Config import took: {time.time() - t0:.4f}s")

print("Phase 4: ChefChat Interface")
t0 = time.time()
from chefchat.interface.app import ChefChatApp
print(f"Interface import took: {time.time() - t0:.4f}s")

print("Phase 5: ChefChat Entrypoint")
t0 = time.time()
from chefchat.cli.entrypoint import main
print(f"Entrypoint import took: {time.time() - t0:.4f}s")

print("Done.")