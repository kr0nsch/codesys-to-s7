"""Блокировки общих ресурсов CODESYS — протокол семейства (00-INDEX.md §4.4).

Класс FileLock — из tools/codesys/cdshost/cli.py (копия plc-repo-template @ da0fc917, тот же код,
что в s7-to-codesys @ 2285760): файл блокировки открывается на дозапись и блокируется по первому
байту (msvcrt.locking в Windows, fcntl.flock в Linux), владелец — JSON в соседнем `.owner`, файл
блокировки не удаляется, блокировку снимает ОС при смерти процесса. Своя реализация через O_EXCL с
ним несовместима, поэтому здесь только обёртки с путями по умолчанию.

    python tools/codesys/lock.py status      # кто держит блокировку рантайма
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cdshost.cli import FileLock  # noqa: E402

__all__ = ["FileLock", "media_kit_lock", "runtime_lock", "runtime_lock_path"]


def _plc_tools_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "plc-tools"


def runtime_lock_path() -> Path:
    return Path(os.environ.get("CDS_RUNTIME_LOCK") or _plc_tools_dir() / "codesys-runtime.lock")


def runtime_lock(purpose: str, timeout_s: float | None = None) -> FileLock:
    timeout = timeout_s if timeout_s is not None else float(os.environ.get("CDS_LOCK_TIMEOUT_S") or 1800)
    return FileLock(runtime_lock_path(), timeout, purpose=purpose)


def media_kit_lock(purpose: str, timeout_s: float = 600) -> FileLock:
    return FileLock(_plc_tools_dir() / "media-kit.lock", timeout_s, purpose=purpose)


if __name__ == "__main__":
    lock = runtime_lock("status", 0)
    print(f"{runtime_lock_path()}: владелец {lock.owner()}")
