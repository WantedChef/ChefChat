import time
import hmac
import hashlib
from urllib.parse import urlencode
from chefchat.bots.telegram.mini_app.auth import verify_init_data, _used_nonces

def generate_valid_init_data(token="test_token", auth_date=None, **kwargs):
    if auth_date is None:
        auth_date = int(time.time())
    
    data = {
        "auth_date": str(auth_date),
        "user": '{"id": 123, "first_name": "Test"}',
        **kwargs
    }
    
    # Calculate hash
    pairs = [f"{k}={v}" for k, v in sorted(data.items(), key=lambda kv: kv[0])]
    data_check_string = "\n".join(pairs)
    
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    
    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    
    data["hash"] = computed_hash
    return urlencode(data)

def test_replay_attack_prevention():
    # Clear nonces
    _used_nonces.clear()
    token = "test_token"
    
    # 1. First attempt - should succeed
    init_data = generate_valid_init_data(token=token)
    assert verify_init_data(init_data=init_data, bot_token=token) == True
    
    # 2. Second attempt with SAME data - should fail (replay)
    assert verify_init_data(init_data=init_data, bot_token=token) == False

def test_expired_auth_date():
    _used_nonces.clear()
    token = "test_token"
    
    # Generate data from 10 minutes ago
    old_time = int(time.time()) - 600
    init_data = generate_valid_init_data(token=token, auth_date=old_time)
    
    assert verify_init_data(init_data=init_data, bot_token=token) == False
