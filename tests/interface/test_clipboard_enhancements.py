"""Tests for clipboard enhancements."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from chefchat.cli.clipboard import (
    copy_text_to_clipboard,
    get_clipboard_available,
    paste_from_clipboard,
)


class TestPasteFromClipboard:
    """Tests for paste_from_clipboard function."""

    @patch("chefchat.cli.clipboard.pyperclip.paste")
    def test_returns_clipboard_text(self, mock_paste: MagicMock) -> None:
        mock_paste.return_value = "hello world"

        result = paste_from_clipboard()

        assert result == "hello world"

    @patch("chefchat.cli.clipboard.pyperclip.paste")
    def test_returns_none_for_empty_clipboard(self, mock_paste: MagicMock) -> None:
        mock_paste.return_value = ""

        result = paste_from_clipboard()

        assert result is None

    @patch("chefchat.cli.clipboard.pyperclip.paste")
    def test_returns_none_on_error(self, mock_paste: MagicMock) -> None:
        mock_paste.side_effect = Exception("Clipboard error")

        result = paste_from_clipboard()

        assert result is None


class TestCopyTextToClipboard:
    """Tests for copy_text_to_clipboard function."""

    @patch("chefchat.cli.clipboard.pyperclip.copy")
    def test_returns_true_on_success(self, mock_copy: MagicMock) -> None:
        result = copy_text_to_clipboard("test text")

        assert result is True
        mock_copy.assert_called_once_with("test text")

    @patch("chefchat.cli.clipboard.pyperclip.copy")
    def test_returns_false_on_error(self, mock_copy: MagicMock) -> None:
        mock_copy.side_effect = Exception("Clipboard error")

        result = copy_text_to_clipboard("test text")

        assert result is False


class TestGetClipboardAvailable:
    """Tests for get_clipboard_available function."""

    @patch("chefchat.cli.clipboard.pyperclip.paste")
    def test_returns_true_when_available(self, mock_paste: MagicMock) -> None:
        mock_paste.return_value = ""

        result = get_clipboard_available()

        assert result is True

    @patch("chefchat.cli.clipboard.pyperclip.paste")
    def test_returns_false_when_unavailable(self, mock_paste: MagicMock) -> None:
        mock_paste.side_effect = Exception("No clipboard available")

        result = get_clipboard_available()

        assert result is False
