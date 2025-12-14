from __future__ import annotations

from unittest.mock import patch

from chefchat.core.utils import get_subprocess_encoding


def test_get_subprocess_encoding_linux():
    with patch("sys.platform", "linux"):
        assert get_subprocess_encoding() == "utf-8"


def test_get_subprocess_encoding_darwin():
    with patch("sys.platform", "darwin"):
        assert get_subprocess_encoding() == "utf-8"


def test_get_subprocess_encoding_windows():
    # We need to ensure ctypes is importable, which it is.
    # But windll is not available on non-Windows.
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
             mock_windll.kernel32.GetOEMCP.return_value = 1252
             assert get_subprocess_encoding() == "cp1252"
