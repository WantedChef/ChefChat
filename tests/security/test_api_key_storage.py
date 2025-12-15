from __future__ import annotations

from unittest.mock import patch

from chefchat.setup.onboarding.screens.api_key import _save_api_key_secure


def test_keyring_storage_preferred():
    with patch("keyring.set_password") as mock_set_pw, \
         patch("chefchat.setup.onboarding.screens.api_key.unset_key") as mock_unset, \
         patch("chefchat.setup.onboarding.screens.api_key.GLOBAL_ENV_FILE") as mock_env_file:
        
        mock_env_file.exists.return_value = True
        
        _save_api_key_secure("TEST_KEY", "secret123")
        
        # Should call set_password
        mock_set_pw.assert_called_once_with("chefchat", "TEST_KEY", "secret123")
        # Should call unset_key to remove from .env
        mock_unset.assert_called_once_with(mock_env_file, "TEST_KEY")

def test_fallback_to_env_on_keyring_failure():
    with patch("keyring.set_password", side_effect=Exception("Keyring failed")), \
         patch("chefchat.setup.onboarding.screens.api_key.set_key") as mock_set_key, \
         patch("chefchat.setup.onboarding.screens.api_key.GLOBAL_ENV_FILE") as mock_env_file:
        
        mock_env_file.parent.exists.return_value = True
        
        _save_api_key_secure("TEST_KEY", "secret123")
        
        # Should fallback to set_key
        mock_set_key.assert_called_once_with(mock_env_file, "TEST_KEY", "secret123")
        # Should try to chmod
        mock_env_file.chmod.assert_called_with(0o600)
