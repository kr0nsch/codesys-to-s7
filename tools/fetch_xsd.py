"""XSD SimaticML (© Siemens AG, «All rights reserved») — только скачивание в .cache/, в git не кладутся.

Источник — копии схем из установок TIA Portal в репозитории dotnetprojects/DotNetSiemensPLCToolBoxLibrary
@ bbe5becc (листинг 19.10.2026, ТЗ M4). Каждый файл проверяется по SHA-256.

    python tools/fetch_xsd.py                  # V19 и V21 → .cache/xsd/<версия>/
    python tools/fetch_xsd.py --matrix         # матрица пространств имён по листингу каталога (печать)
    python tools/fetch_xsd.py --check          # только проверить уже скачанное
Переменная C2S7_XSD_DIR переопределяет каталог.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OWNER_REPO = "dotnetprojects/DotNetSiemensPLCToolBoxLibrary"
SHA = "bbe5beccbadcf7497408e92883e260cc5024a874"
BASE = f"https://raw.githubusercontent.com/{OWNER_REPO}/{SHA}/externalDlls/siemens"

# SHA-256 файлов, посчитанные при первом скачивании 20.10.2026 (доверие при первом использовании)
FILES: dict[str, dict[str, str]] = {
    "V19": {
        "SW.Common_v3.xsd": "183d17bcdab57ec465c2ff744fafb94a89caf217ad642562e68b740d18966f53",
        "SW.InterfaceSections_v5.xsd": "6e3dfc80d9709b0a0497224b2bb269fe34322659cd2c98e92bb68a99d71901e8",
        "SW.PlcBlocks.Access_v5.xsd": "5b29b6cd965b123f35b8e6916f7f412b8bd4b476858e11bfeabace020aea557d",
        "SW.PlcBlocks.CompileUnitCommon_v5.xsd": "38c7e4b87efabe370e67665a42ebc1693df2781c241408d7aa825051403714b9",
        "SW.PlcBlocks.Graph_v6.xsd": "6632f3676254f20087c3bb63469923f5863453ed08c42cb2fa6ed6702becfa0e",
        "SW.PlcBlocks.LADFBD_v5.xsd": "e5a32746784452e400ca2a73fedb7a750950ce51632d8151aba7dc8d039a8c8f",
        "SW.PlcBlocks.SCL_v4.xsd": "7d45d5174aa5a11d3e4f1579a2eed2cc74fff38f5853129e0d3f98342550f2b0",
        "SW.PlcBlocks.STL_v5.xsd": "77c05b2fcf3b621ee18fc76c9be2817f7d53a7e3ccf5860252a02e1f2fcb4c14",
    },
    "V21": {
        "SW.Common_v3.xsd": "f4d9aa76f9a49bfe14b4268d79ba8cdc9f5f2aeeed505017bd01cdcfee587655",
        "SW.InterfaceSections_v5.xsd": "c3b4735c1acbd29690afdaa13d11586ac7973ffa96d8f6fbe20d4f3b4490be56",
        "SW.PlcBlocks.Access_v5.xsd": "7d814f8ce7225d06d7764d3bdf6bfaf2fa179121c45a3e0f1334b65314562932",
        "SW.PlcBlocks.CompileUnitCommon_v5.xsd": "a55583fd2c5e26f65a4a9a8bc47d54c620c3820c9e9aecdc12dfc724e01642c0",
        "SW.PlcBlocks.Graph_v6.xsd": "49e3f5589e30b7bcef3c66e9a322b85d6cc4408a5d2b24e0db50d519df0390d1",
        "SW.PlcBlocks.LADFBD_v5.xsd": "223f0a318e035ede17e4147eae598fea1785696e89df374dab5edc67db2cf2cd",
        "SW.PlcBlocks.SCL_v4.xsd": "7fd1ec64f230b2d6adde2d70131077d6589b34479f5fecdf16d39dad848412e4",
        "SW.PlcBlocks.STL_v5.xsd": "f870e11c49a2e5b34e5252abbfacc0f8c5ac0d87fa23fc2526213b3cbf617a20",
    },
}

# Листинг каталогов Schemas @ bbe5becc (gh api, 19–20.10.2026): по нему строится матрица версий схем
LISTING: dict[str, list[str]] = {
    "V15.1": [
        "SW.InterfaceSections_v3",
        "SW.PlcBlocks.LADFBD_v3",
        "SW.PlcBlocks.SCL_v2",
        "SW.PlcBlocks.Graph_v4",
        "SW.PlcBlocks.Access_v3",
    ],
    "V16": [
        "SW.InterfaceSections_v4",
        "SW.PlcBlocks.LADFBD_v4",
        "SW.PlcBlocks.SCL_v3",
        "SW.PlcBlocks.Graph_v5",
        "SW.PlcBlocks.Access_v4",
    ],
    "V17": [
        "SW.InterfaceSections_v4",
        "SW.InterfaceSections_v5",
        "SW.PlcBlocks.LADFBD_v4",
        "SW.PlcBlocks.SCL_v3",
        "SW.PlcBlocks.Graph_v5",
        "SW.PlcBlocks.Access_v4",
    ],
    "V18": [
        "SW.InterfaceSections_v5",
        "SW.PlcBlocks.LADFBD_v4",
        "SW.PlcBlocks.SCL_v3",
        "SW.PlcBlocks.Graph_v5",
        "SW.PlcBlocks.Access_v4",
    ],
    "V19": [
        "SW.InterfaceSections_v5",
        "SW.PlcBlocks.LADFBD_v5",
        "SW.PlcBlocks.SCL_v4",
        "SW.PlcBlocks.Graph_v6",
        "SW.PlcBlocks.Access_v5",
    ],
    "V20": [
        "SW.InterfaceSections_v5",
        "SW.PlcBlocks.LADFBD_v4",
        "SW.PlcBlocks.SCL_v3",
        "SW.PlcBlocks.Graph_v5",
        "SW.PlcBlocks.Access_v4",
    ],
    "V21": [
        "SW.InterfaceSections_v5",
        "SW.PlcBlocks.LADFBD_v5",
        "SW.PlcBlocks.SCL_v4",
        "SW.PlcBlocks.Graph_v6",
        "SW.PlcBlocks.Access_v5",
    ],
}

_KEYS = {
    "SW.InterfaceSections": "interface",
    "SW.PlcBlocks.LADFBD": "flgnet",
    "SW.PlcBlocks.SCL": "scl",
    "SW.PlcBlocks.Graph": "graph",
    "SW.PlcBlocks.Access": "access",
}


def xsd_dir() -> Path:
    return Path(os.environ.get("C2S7_XSD_DIR") or REPO / ".cache" / "xsd")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix() -> dict[str, dict[str, str]]:
    """Версии схем по версии TIA: {"V19": {"interface": "v5", ...}}; при нескольких — через «+»."""
    out: dict[str, dict[str, str]] = {}
    for tia, names in LISTING.items():
        row: dict[str, list[str]] = {}
        for n in names:
            m = re.match(r"(.+)_(v\d+)$", n)
            if m and m.group(1) in _KEYS:
                row.setdefault(_KEYS[m.group(1)], []).append(m.group(2))
        out[tia] = {k: "+".join(sorted(v)) for k, v in row.items()}
    return out


def fetch(versions: list[str], check_only: bool = False) -> list[str]:
    problems: list[str] = []
    for ver in versions:
        for name, digest in FILES[ver].items():
            path = xsd_dir() / ver / name
            if not path.exists():
                if check_only:
                    problems.append(f"нет {path}")
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                url = f"{BASE}/{ver}/Schemas/{name}"
                with urllib.request.urlopen(url, timeout=60) as resp:
                    data = resp.read()
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                if hashlib.sha256(data).hexdigest() != digest:
                    tmp.unlink()
                    problems.append(f"SHA-256 не совпал: {url}")
                    continue
                tmp.replace(path)
            elif sha256(path) != digest:
                problems.append(f"SHA-256 не совпал: {path}")
    return problems


def available(version: str) -> Path | None:
    """Каталог схем версии, если все файлы на месте и совпадают по SHA-256."""
    base = xsd_dir() / version
    if version not in FILES:
        return None
    for name, digest in FILES[version].items():
        p = base / name
        if not p.exists() or sha256(p) != digest:
            return None
    return base


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", action="store_true", help="напечатать матрицу версий схем")
    ap.add_argument("--check", action="store_true", help="только проверить скачанное")
    ap.add_argument("versions", nargs="*", default=["V19", "V21"])
    args = ap.parse_args(argv)
    if args.matrix:
        print(json.dumps(matrix(), indent=2, ensure_ascii=False))
        return 0
    problems = fetch(args.versions, check_only=args.check)
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f"XSD {', '.join(args.versions)}: {xsd_dir()}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
