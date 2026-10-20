"""Прогон в CODESYS Control Win под общей блокировкой рантайма (Python 3, Windows).

Блокировка — класс FileLock из скопированного tools/codesys/cdshost/cli.py (протокол семейства:
`%LOCALAPPDATA%\\plc-tools\\codesys-runtime.lock`, первый байт через msvcrt.locking, владелец — в
`.owner`; 00-INDEX.md §4.4). Рантайм общий для нескольких проектов, поэтому:
- уже запущенный рантайм используется как есть и не перезапускается;
- если рантайма нет, он запускается и после прогона останавливается (только тот, что запущен здесь);
- рантайм, которому до конца демо-режима (2 ч) меньше 10 минут, не используется — RuntimeBusy;
- блокировку не дали за CDS_LOCK_TIMEOUT_S — RuntimeBusy (тесты дают skip «runtime busy»).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cdshost import cli as H  # noqa: E402

JOB_ENV = "C2S7_JOB"


class RuntimeBusy(RuntimeError):
    """Рантайм занят другим процессом дольше тайм-аута или близок к концу демо-режима."""


def settings() -> Any:
    return H.make_settings(REPO)


def lock_timeout() -> float:
    return float(os.environ.get("CDS_LOCK_TIMEOUT_S") or 1800)


def run_script(script: str, job: dict[str, Any], label: str, timeout_s: float = 900, online: bool = False) -> dict[str, Any]:
    """Скрипт CODESYS из tools/codesys; online=True — под блокировкой рантайма с проверкой рантайма."""
    sys.path.insert(0, str(REPO / "tools" / "probes"))
    import cdsrun

    work = REPO / "build" / "cds"
    if not online:
        return cdsrun.run(HERE / script, job, work, label, timeout_s)
    st = settings()
    lock = H.FileLock(st.path("lock.path"), lock_timeout(), purpose=f"c2s7 {label}")
    try:
        lock.acquire()
    except H.CdsError as exc:
        raise RuntimeBusy(str(exc)) from None
    started_here = False
    try:
        status = H.runtime_status(st)
        if status["running"]:
            left = status.get("demo_left_min")
            if left is not None and left < 10:
                raise RuntimeBusy(f"рантайм работает {status['age_min']} мин: до конца демо-режима {left} мин")
        elif status["port_open"]:
            pass  # сторонний экземпляр — используем как есть
        else:
            H.runtime_start(st)
            started_here = True
        job = dict(job)
        online_spec = dict(job.get("online", {}))
        online_spec.setdefault("credentials", str(st.path("runtime.credentials")))
        online_spec.setdefault(
            "runtime",
            {
                "gateway_name": str(st.value("runtime.gateway.name")),
                "gateway_host": str(st.value("runtime.gateway.host")),
                "gateway_port": int(st.number("runtime.gateway.port")),
                "device_address": str(st.value("runtime.device_address")),
                "device_port": int(st.number("runtime.port")),
            },
        )
        job["online"] = online_spec
        result = cdsrun.run(HERE / script, job, work, label, timeout_s)
        result["runtime"] = {"started_here": started_here, "status": status}
        return result
    finally:
        if started_here:
            H.runtime_stop(st)
        lock.release()
