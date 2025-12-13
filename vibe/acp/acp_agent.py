from __future__ import annotations

import sys

import chefchat.acp.acp_agent as _acp_agent

# Expose the real module under the legacy import path so patching
# `vibe.acp.acp_agent.*` also patches `chefchat.acp.acp_agent.*`.
sys.modules[__name__] = _acp_agent
