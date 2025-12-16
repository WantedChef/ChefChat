from __future__ import annotations

import fcntl
import os
from pathlib import Path


class FileLock:
    """Simple file lock for single-instance protection."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._handle: int | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return

        fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RuntimeError(
                f"Telegram bot already running (lock busy): {self.lock_path}"
            )

        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.fsync(fd)
        self._handle = fd

    def release(self) -> None:
        if self._handle is None:
            return

        try:
            fcntl.flock(self._handle, fcntl.LOCK_UN)
        finally:
            os.close(self._handle)
            self._handle = None
