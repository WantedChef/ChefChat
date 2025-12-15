from __future__ import annotations

import logging

from chefchat.core.config import Backend
from chefchat.core.llm.backend.generic import GenericBackend
from chefchat.core.llm.backend.mistral import MistralBackend

logger = logging.getLogger(__name__)

BACKEND_FACTORY = {Backend.MISTRAL: MistralBackend, Backend.GENERIC: GenericBackend}


def get_backend_cls(backend: Backend):
    """Return backend class with a safe fallback."""
    if backend in BACKEND_FACTORY:
        return BACKEND_FACTORY[backend]
    logger.warning("Unknown backend '%s', falling back to GenericBackend", backend)
    return GenericBackend
