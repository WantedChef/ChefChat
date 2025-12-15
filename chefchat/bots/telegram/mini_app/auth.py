from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl

# Nonce storage: hash -> timestamp
_used_nonces: dict[str, float] = {}


def _cleanup_old_nonces(max_age_seconds: int) -> None:
    """Remove expired nonces from memory efficiently."""
    now = time.time()
    # More efficient: delete expired nonces directly in one pass
    expired_nonces = [
        nonce
        for nonce, timestamp in _used_nonces.items()
        if now - timestamp > max_age_seconds
    ]
    for nonce in expired_nonces:
        del _used_nonces[nonce]


def verify_init_data(
    *, init_data: str, bot_token: str, max_age_seconds: int = 300
) -> bool:
    """Verify Telegram Mini App initData signature.

    Uses Telegram WebAppData verification algorithm.

    Includes replay protection:
    - Checks auth_date freshness
    - Tracks used hashes (nonces) to prevent reuse within window
    """
    if not init_data or not bot_token:
        return False

    items = list(parse_qsl(init_data, keep_blank_values=True))
    data = {k: v for k, v in items}

    recv_hash = data.pop("hash", "")
    if not recv_hash:
        return False

    auth_date_raw = data.get("auth_date", "")
    try:
        auth_date = int(auth_date_raw)
    except Exception:
        return False

    if max_age_seconds > 0 and (time.time() - auth_date) > max_age_seconds:
        return False

    # REPLAY PROTECTION: Check if nonce (hash) already used
    if recv_hash in _used_nonces:
        return False

    # Sort by key and build the data_check_string
    pairs = [f"{k}={v}" for k, v in sorted(data.items(), key=lambda kv: kv[0])]
    data_check_string = "\n".join(pairs)

    secret_key = hmac.new(
        key=b"WebAppData", msg=bot_token.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()

    computed_hash = hmac.new(
        key=secret_key, msg=data_check_string.encode("utf-8"), digestmod=hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(computed_hash, recv_hash)

    if is_valid:
        # Store nonce to prevent replay
        _used_nonces[recv_hash] = time.time()
        # Periodic cleanup (amortized cost) with lower threshold for better memory management
        if len(_used_nonces) > 500:  # Lower threshold for more frequent cleanup
            _cleanup_old_nonces(max_age_seconds)

    return is_valid
