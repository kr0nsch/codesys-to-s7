"""Запуск своих скриптов CODESYS (IronPython) из Python 3: задание JSON → noUI → результат JSON.

Командная строка собирается одной строкой с буквальными кавычками после `--profile=` (иначе CODESYS
не видит профиль в noUI — VERIFIED_codesys_env.md). Путь к CODESYS и профиль — из переменных
окружения CODESYS_EXE / CODESYS_PROFILE или по умолчанию для 3.5.17.30.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
JOB_ENV = "C2S7_JOB"
DEFAULT_EXE = r"C:\Program Files (x86)\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe"
DEFAULT_PROFILE = "CODESYS V3.5 SP17 Patch 3"
CONTROL_WIN = {"type": 4096, "id": "0000 0001", "version": "3.5.17.30"}


class CdsRunError(RuntimeError):
    pass


def codesys_exe() -> Path:
    return Path(os.environ.get("CODESYS_EXE") or DEFAULT_EXE)


def codesys_profile() -> str:
    return os.environ.get("CODESYS_PROFILE") or DEFAULT_PROFILE


def available() -> bool:
    """CODESYS установлен (только Windows)."""
    return sys.platform == "win32" and codesys_exe().is_file()


def cmdline(script: Path) -> str:
    exe, profile = str(codesys_exe()), codesys_profile()
    for value in (exe, profile, str(script)):
        if '"' in value:
            raise CdsRunError(f"недопустимая кавычка: {value!r}")
    return f'"{exe}" --profile="{profile}" --noUI --runscript="{script}"'


def run(script: Path, job: dict[str, Any], work: Path, label: str, timeout_s: float = 900) -> dict[str, Any]:
    """Запускает скрипт CODESYS с заданием; возвращает результат (поле job['result'])."""
    work.mkdir(parents=True, exist_ok=True)
    job_path = work / f"job-{label}.json"
    result_path = work / f"result-{label}.json"
    stdout_path = work / f"{label}.stdout.log"
    if result_path.exists():
        result_path.unlink()
    job = dict(job, result=str(result_path))
    job_path.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ)
    env[JOB_ENV] = str(job_path)
    started = time.time()
    print(f"[cds] {codesys_profile()}: {script.name} ({label}) ...", flush=True)
    proc = subprocess.Popen(
        cmdline(script),
        cwd=str(work),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        out, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        out, _ = proc.communicate()
        stdout_path.write_bytes(out or b"")
        raise CdsRunError(f"CODESYS не завершился за {timeout_s:.0f} с; вывод: {stdout_path}") from None
    stdout_path.write_bytes(out or b"")
    if not result_path.exists():
        raise CdsRunError(f"CODESYS (код {proc.returncode}) не записал {result_path}; вывод: {stdout_path}")
    result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    result["elapsed_s"] = round(time.time() - started, 1)
    result["process_exit_code"] = proc.returncode
    return result
