"""Tests for ShellIntegration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from chefchat.cli.shell_integration import ShellIntegration


class TestDetectShell:
    """Tests for shell detection."""

    def test_detects_zsh(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            assert ShellIntegration.detect_shell() == "zsh"

    def test_detects_bash(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            assert ShellIntegration.detect_shell() == "bash"

    def test_detects_fish(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            assert ShellIntegration.detect_shell() == "fish"

    def test_detects_from_path_basename(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/usr/local/bin/zsh"}):
            assert ShellIntegration.detect_shell() == "zsh"

    def test_returns_unknown_for_unrecognized_shell(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/custom-shell"}):
            assert ShellIntegration.detect_shell() == "unknown"


class TestGetHistoryFile:
    """Tests for history file detection."""

    def test_returns_zsh_history_for_zsh(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}, clear=True):
            with patch.dict("os.environ", {"HISTFILE": ""}, clear=False):
                path = ShellIntegration.get_history_file()
                assert path is not None
                assert path.name == ".zsh_history"

    def test_returns_bash_history_for_bash(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}, clear=True):
            with patch.dict("os.environ", {"HISTFILE": ""}, clear=False):
                path = ShellIntegration.get_history_file()
                assert path is not None
                assert path.name == ".bash_history"

    def test_respects_histfile_env_var(self) -> None:
        custom_path = "/custom/history"
        with patch.dict("os.environ", {"SHELL": "/bin/bash", "HISTFILE": custom_path}):
            path = ShellIntegration.get_history_file()
            assert path == Path(custom_path)


class TestReadHistory:
    """Tests for reading shell history."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_reads_simple_history(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "ls\ncd /tmp\necho hello\n"

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            history = ShellIntegration.read_history(limit=10)

        assert "ls" in history
        assert "cd /tmp" in history
        assert "echo hello" in history

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_parses_zsh_extended_format(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = ": 1234567890:0;ls -la\n: 1234567891:0;cd /tmp\n"

        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            history = ShellIntegration.read_history()

        assert "ls -la" in history
        assert "cd /tmp" in history

    @patch("pathlib.Path.exists")
    def test_returns_empty_if_file_missing(self, mock_exists: MagicMock) -> None:
        mock_exists.return_value = False

        history = ShellIntegration.read_history()

        assert history == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_deduplicates_history(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "ls\ncd\nls\nls\ncd\n"

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            history = ShellIntegration.read_history()

        # Should be deduplicated
        assert history.count("ls") == 1
        assert history.count("cd") == 1

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_respects_limit(self, mock_read: MagicMock, mock_exists: MagicMock) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "\n".join([f"command{i}" for i in range(100)])

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            history = ShellIntegration.read_history(limit=5)

        assert len(history) <= 5


class TestGenerateAliases:
    """Tests for alias generation."""

    def test_generates_bash_aliases(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            aliases = ShellIntegration.generate_aliases()

        assert "alias chef=" in aliases
        assert "alias cheftui=" in aliases
        assert "uv run vibe" in aliases

    def test_generates_fish_aliases(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            aliases = ShellIntegration.generate_aliases()

        # Fish uses different syntax (no = sign)
        assert "alias chef " in aliases
        assert "alias cheftui " in aliases


class TestGetRcFile:
    """Tests for rc file detection."""

    def test_returns_zshrc_for_zsh(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            path = ShellIntegration.get_rc_file()
            assert path is not None
            assert path.name == ".zshrc"

    def test_returns_bashrc_for_bash(self) -> None:
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            with patch.object(Path, "exists", return_value=False):
                path = ShellIntegration.get_rc_file()
                assert path is not None
                assert path.name == ".bashrc"


class TestInstallAliases:
    """Tests for alias installation."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.write_text")
    def test_installs_aliases_to_empty_file(
        self, mock_write: MagicMock, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = ""

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = ShellIntegration.install_aliases(Path("/tmp/testrc"))

        assert result is True
        mock_write.assert_called_once()
        written_content = mock_write.call_args[0][0]
        assert "# >>> ChefChat Integration >>>" in written_content
        assert "# <<< ChefChat Integration <<<" in written_content

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.write_text")
    def test_updates_existing_installation(
        self, mock_write: MagicMock, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = """
# Some existing content
# >>> ChefChat Integration >>>
old aliases
# <<< ChefChat Integration <<<
# More content
"""

        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = ShellIntegration.install_aliases(Path("/tmp/testrc"))

        assert result is True
        written_content = mock_write.call_args[0][0]
        # Should have updated the block, not added a new one
        assert written_content.count("# >>> ChefChat Integration >>>") == 1


class TestUninstallAliases:
    """Tests for alias removal."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.write_text")
    def test_removes_aliases(
        self, mock_write: MagicMock, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = """
# Some content
# >>> ChefChat Integration >>>
alias chef='uv run vibe'
# <<< ChefChat Integration <<<
# More content
"""

        result = ShellIntegration.uninstall_aliases(Path("/tmp/testrc"))

        assert result is True
        written_content = mock_write.call_args[0][0]
        assert "# >>> ChefChat Integration >>>" not in written_content

    @patch("pathlib.Path.exists")
    def test_returns_false_if_file_missing(self, mock_exists: MagicMock) -> None:
        mock_exists.return_value = False

        result = ShellIntegration.uninstall_aliases(Path("/tmp/testrc"))

        # Returns False when file doesn't exist - nothing to uninstall from
        assert result is False


class TestIsInstalled:
    """Tests for installation check."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_returns_true_if_installed(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "# >>> ChefChat Integration >>>"

        result = ShellIntegration.is_installed(Path("/tmp/testrc"))

        assert result is True

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_returns_false_if_not_installed(
        self, mock_read: MagicMock, mock_exists: MagicMock
    ) -> None:
        mock_exists.return_value = True
        mock_read.return_value = "# Some other content"

        result = ShellIntegration.is_installed(Path("/tmp/testrc"))

        assert result is False
