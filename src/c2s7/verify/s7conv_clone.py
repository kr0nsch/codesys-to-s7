"""Клон s7-to-codesys @ 2285760c — единственный источник s7conv, stsim, MAPPING.md и сценариев (ТЗ M10).

Проверки: `git rev-parse HEAD` = SHA и пустой `git status --porcelain`, иначе код 2. Каталог —
`.cache/s7-to-codesys@2285760c` или переменная S7_TO_CODESYS_DIR (на такой же клон). Живой каталог
asu_TP/s7-to-codesys не используется: его меняет проект 00.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SHA = "2285760c1c99ce4218d5356c75e93111828f8e3b"
REPO_URL = "https://github.com/kr0nsch/s7-to-codesys.git"


class CloneError(RuntimeError):
    """Клон отсутствует или не на закреплённом коммите (код CLI 2)."""


def default_dir(base: Path | None = None) -> Path:
    env = os.environ.get("S7_TO_CODESYS_DIR")
    if env:
        return Path(env)
    root = base or Path.cwd()
    return root / ".cache" / "s7-to-codesys@2285760c"


def _git(path: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise CloneError(f"git {' '.join(args)} в {path}: {proc.stderr.strip()}")
    return proc.stdout


def check(path: Path) -> Path:
    """Проверка клона; возвращает абсолютный путь."""
    if not (path / "s7conv" / "__init__.py").exists():
        raise CloneError(
            f"нет клона s7-to-codesys в {path}: git clone {REPO_URL} {path} && git -C {path} checkout {SHA}"
        )
    head = _git(path, "rev-parse", "HEAD").strip()
    if head != SHA:
        raise CloneError(f"клон {path} на {head[:12]}, нужен {SHA[:12]}")
    dirty = _git(path, "status", "--porcelain").strip()
    if dirty:
        raise CloneError(f"в клоне {path} есть изменения:\n{dirty[:500]}")
    return path.resolve()


def ensure(path: Path, allow_clone: bool = False) -> Path:
    """Проверка; при allow_clone — клонирование с GitHub (для CI)."""
    if not (path / "s7conv").exists() and allow_clone:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", REPO_URL, str(path)], check=True)
        subprocess.run(["git", "-C", str(path), "-c", "advice.detachedHead=false", "checkout", "-q", SHA], check=True)
    return check(path)


def import_s7conv(path: Path, module: str = "s7conv.parser") -> ModuleType:
    """Модуль s7conv из клона (через sys.path; пакет s7conv не устанавливается)."""
    root = str(path.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(module)
