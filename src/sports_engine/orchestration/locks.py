import os
import sys
from ctypes import windll
from pathlib import Path
from types import TracebackType


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode())
        except FileExistsError as exc:
            owner = self._owner_pid()
            if owner is None or _process_exists(owner):
                raise RuntimeError(f"Job lock is already held: {self.path}") from exc
            # The recorded process no longer exists. Removing this exact lock
            # file is safe because O_EXCL prevented another owner from taking
            # it between inspection and this retry.
            self.path.unlink()
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode())
        return self

    def _owner_pid(self) -> int | None:
        try:
            value = int(self.path.read_text(encoding="ascii").strip())
        except (OSError, UnicodeError, ValueError):
            return None
        return value if value > 0 else None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


def _process_exists(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        handle = windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
