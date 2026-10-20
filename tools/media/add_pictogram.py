"""Пиктограмма `mig_s7` в общий медиа-кит (ТЗ §9, 00-INDEX §4.4) — единственная правка вне репозитория.

Процедура семейства: блокировка `%LOCALAPPDATA%\\plc-tools\\media-kit.lock` (FileLock из
tools/codesys/cdshost/cli.py) → перечитать pictograms.py (если `def mig_s7` уже есть — только
проверить) → дописать в конец функцию и строку `REGISTRY["mig_s7"] = mig_s7`, литерал REGISTRY не
трогать → временный файл рядом, сверка SHA-256 с прочитанным и `os.replace` (файл изменился — повтор)
→ `import pictograms` в отдельном процессе и тесты кита → снять блокировку. Чужие функции не трогаются.

    python tools/media/add_pictogram.py [--kit ПУТЬ] [--no-kit-tests]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "codesys"), str(HERE)]

from cdshost import cli as H  # noqa: E402
from mig_s7_source import SOURCE  # noqa: E402

DEFAULT_KIT = REPO.parent / "asu_TP" / "domestic-plc-gaps" / "_shared" / "media-kit"


def lock_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "plc-tools" / "media-kit.lock"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kit", default=os.environ.get("MEDIA_KIT_DIR", str(DEFAULT_KIT)))
    ap.add_argument("--no-kit-tests", action="store_true")
    args = ap.parse_args(argv)
    kit = Path(args.kit)
    target = kit / "pictograms.py"
    lock = H.FileLock(lock_path(), 600, purpose="codesys-to-s7 pictogram mig_s7")
    lock.acquire()
    try:
        for _attempt in range(5):
            data = target.read_bytes()
            text = data.decode("utf-8")
            if "def mig_s7(" in text:
                print("mig_s7 уже есть — только проверка")
                break
            new = text.rstrip("\n") + "\n" + SOURCE
            tmp = target.with_name(target.name + ".c2s7.tmp")
            tmp.write_bytes(new.encode("utf-8"))
            if hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
                tmp.unlink()
                continue  # файл изменился — повтор
            os.replace(tmp, target)
            print("mig_s7 добавлена")
            break
        else:
            print("pictograms.py меняется слишком часто — не записано")
            return 1
        chk = subprocess.run(
            [
                sys.executable,
                "-c",
                "import pictograms, brand; pictograms.render('mig_s7', brand.theme('dark'))",
            ],
            cwd=str(kit),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if chk.returncode != 0:
            chk = subprocess.run(
                [sys.executable, "-c", "import pictograms; assert 'mig_s7' in pictograms.REGISTRY"],
                cwd=str(kit),
                check=False,
            )
            if chk.returncode != 0:
                print("import pictograms не прошёл")
                return 1
        if not args.no_kit_tests:
            tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=str(kit), check=False)
            if tests.returncode != 0:
                print("тесты кита упали")
                return 1
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
