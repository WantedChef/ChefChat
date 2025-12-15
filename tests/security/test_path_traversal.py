from __future__ import annotations

from chefchat.core.autocompletion.path_prompt import PathResource, _to_resource


def test_blocks_parent_directory_traversal(tmp_path):
    base = tmp_path / "safe"
    base.mkdir()
    secret = tmp_path / "secret.txt"
    secret.touch()

    # Test "../secret.txt" attempt
    result = _to_resource("../secret.txt", base)
    assert result is None


def test_blocks_absolute_path_escape(tmp_path):
    base = tmp_path / "safe"
    base.mkdir()
    # Test absolute path attempt
    result = _to_resource("/etc/passwd", base)
    assert result is None


def test_allows_valid_paths(tmp_path):
    base = tmp_path / "safe"
    base.mkdir()
    valid_file = base / "file.txt"
    valid_file.touch()

    result = _to_resource("file.txt", base)
    assert result is not None
    assert isinstance(result, PathResource)
    assert result.path == valid_file.resolve()
