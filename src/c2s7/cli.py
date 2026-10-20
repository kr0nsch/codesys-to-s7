"""Командная строка c2s7 (ТЗ M11).

Коды выхода: 0 — успех; 1 — находки не ниже --fail-on (analyze, migrate) или расхождения (verify);
2 — ошибка ввода, профиля или клона s7conv.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from c2s7 import TOOL, __version__
from c2s7.convert.core import Options, Result
from c2s7.ingest.common import IngestError
from c2s7.profiles import ProfileError
from c2s7.rules import SEVERITY, registry
from c2s7.st.parser import StSyntaxError

EXIT_OK, EXIT_FINDINGS, EXIT_INPUT = 0, 1, 2

EPILOG = """\
примеры:
  c2s7 inventory project.xml
  c2s7 analyze project.xml --cpu s7-1200 --tia V19
  c2s7 migrate project.xml --out out/project --cpu s7-1500 --tia V21 --zip out/project.zip
  c2s7 migrate tests/fixtures/s7-to-codesys --out out/ring
  c2s7 verify out/ring --roundtrip
  c2s7 explain C2S7-SEM-SRRS
"""


def _cpu_tia(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--cpu", choices=("s7-1200", "s7-1500"), default="s7-1500", help="CPU цели (S7-1200 G2 не поддерживается)"
    )
    p.add_argument("--tia", default="V21", help="версия TIA Portal: V19, V21 (P0); V15.1–V18 — только SCL")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="c2s7",
        description="Перенос проектов CODESYS 3.5 в Siemens S7-1200/1500 (TIA Portal): SCL, DB, UDT, SimaticML, теги, отчёт.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"c2s7 {__version__}")
    sub = ap.add_subparsers(dest="cmd", metavar="КОМАНДА")
    sub.required = True

    inv = sub.add_parser("inventory", help="состав проекта: POU по языкам, GVL, DUT, задачи")
    inv.add_argument("input")
    inv.add_argument("--format", choices=("text", "json"), default="text")

    an = sub.add_parser("analyze", help="классы конструкций и находки без записи файлов")
    an.add_argument("input")
    _cpu_tia(an)
    an.add_argument("--format", choices=("text", "json", "md", "html"), default="text")
    an.add_argument("--fail-on", choices=("manual", "verify", "never"), default="manual")
    an.add_argument("--io-map", help="CSV «Export mappings to CSV» устройства CODESYS")

    mg = sub.add_parser("migrate", help="перенос: tia/, roundtrip/, отчёт")
    mg.add_argument("input")
    mg.add_argument("--out", required=True)
    _cpu_tia(mg)
    mg.add_argument("--io-map")
    mg.add_argument("--graphics", choices=("scl", "simaticml", "sd"))
    mg.add_argument("--sfc", choices=("scl", "graph"), default="scl")
    mg.add_argument("--cfc", choices=("scl", "fbd"), default="scl")
    mg.add_argument("--timers", choices=("native", "compat"), default="native")
    mg.add_argument("--edges", choices=("native", "compat"), default="native")
    mg.add_argument("--markers", choices=("db", "keep"), default="db")
    mg.add_argument("--cds-bit-addressing", choices=("byte", "word"), default="byte")
    mg.add_argument("--range-check", action="store_true")
    mg.add_argument("--max-ob-priority", type=int, default=15)
    mg.add_argument("--ob-from-tasks", action="store_true")
    mg.add_argument("--bundle", action="store_true", help="добавить tia/sources/all.scl")
    mg.add_argument("--zip")
    mg.add_argument("--fail-on", choices=("manual", "verify", "never"), default="never")

    vf = sub.add_parser("verify", help="обратная проверка результата migrate")
    vf.add_argument("out")
    vf.add_argument("--roundtrip", action="store_true", help="s7conv @ 2285760c → ST′ → оракул")
    vf.add_argument("--regime", choices=("r1", "r2"), default="r1")
    vf.add_argument("--oracle", choices=("sim", "stsim", "codesys", "plc-code"), default="sim")
    vf.add_argument("--scenarios", help="каталог сценариев CSV (по умолчанию — scenarios/ рядом с входом)")
    vf.add_argument("--s7conv", help="клон s7-to-codesys @ 2285760c (по умолчанию .cache/ или S7_TO_CODESYS_DIR)")

    pr = sub.add_parser("probe", help="пробник TIA: SCL на каждую verify-конструкцию (из результата migrate)")
    pr.add_argument("out")

    rd = sub.add_parser("render", help="SVG схемы POU (источник и цель)")
    rd.add_argument("input")
    rd.add_argument("--pou", required=True)
    rd.add_argument("--out", required=True)
    _cpu_tia(rd)

    ex = sub.add_parser("explain", help="описание правила C2S7-*")
    ex.add_argument("rule")

    st = sub.add_parser("site", help="статический сайт-просмотрщик (Pages)")
    st.add_argument("--out", default="site-out")
    st.add_argument("--cases", nargs="*", help="каталоги результатов migrate (по умолчанию — из site/cases.json)")
    return ap


def _options(args: argparse.Namespace) -> Options:
    return Options(
        cpu=args.cpu,
        tia=args.tia,
        graphics=getattr(args, "graphics", None),
        sfc=getattr(args, "sfc", "scl"),
        cfc=getattr(args, "cfc", "scl"),
        timers=getattr(args, "timers", "native"),
        edges=getattr(args, "edges", "native"),
        markers=getattr(args, "markers", "db"),
        bit_addressing=getattr(args, "cds_bit_addressing", "byte"),
        range_check=getattr(args, "range_check", False),
        max_ob_priority=getattr(args, "max_ob_priority", 15),
        ob_from_tasks=getattr(args, "ob_from_tasks", False),
    )


def _fail(res: Result, level: str) -> bool:
    if level == "never":
        return False
    thr = SEVERITY[level]
    return any(SEVERITY[f.outcome] >= thr for f in res.collector.findings if f.outcome != "info")


def cmd_inventory(args: argparse.Namespace) -> int:
    from c2s7.api import load_input

    proj = load_input(Path(args.input))
    data = {
        "input": proj.path,
        "kind": proj.kind,
        "sha256": proj.sha256,
        "pous": [{"name": p.name, "kind": p.kind, "language": p.language} for p in proj.pous],
        "gvls": [g.name for g in proj.gvls],
        "duts": [d.name for d in proj.duts],
        "tasks": [
            {"name": t.name, "kind": t.kind, "interval_ms": t.interval_ms, "priority": t.priority, "pous": t.pous}
            for t in proj.tasks
        ],
        "libraries": [lib.name for lib in proj.libraries],
    }
    if args.format == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return EXIT_OK
    langs: dict[str, int] = {}
    for p in proj.pous:
        langs[p.language] = langs.get(p.language, 0) + 1
    print(f"{proj.path}: {proj.kind}, SHA-256 {proj.sha256[:12]}…")
    print(
        f"POU: {len(proj.pous)} ({', '.join(f'{k} {v}' for k, v in sorted(langs.items()))}); GVL: {len(proj.gvls)}; DUT: {len(proj.duts)}; задач: {len(proj.tasks)}"
    )
    for p in proj.pous:
        print(f"  {p.kind:<15} {p.name:<28} {p.language}")
    for t in proj.tasks:
        iv = f"{t.interval_ms:g} мс" if t.interval_ms else t.kind
        print(f"  задача {t.name}: {iv}, приоритет {t.priority}: {', '.join(t.pous)}")
    return EXIT_OK


def cmd_analyze(args: argparse.Namespace) -> int:
    from c2s7.api import load_input, migrate
    from c2s7.emit import report as R
    from c2s7.ingest.iomap import load_io_map

    proj = load_input(Path(args.input))
    opts = _options(args)
    if args.io_map:
        opts.io_map = load_io_map(Path(args.io_map))
    res = migrate(proj, opts)
    data = R.report_json(res, [])
    if args.format == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.format == "md":
        print(R.report_md(data))
    elif args.format == "html":
        print(R.report_html(data))
    else:
        t = data["totals"]["by_outcome"]
        print(f"{TOOL}: {proj.path} → {res.profile.title}, TIA {res.profile.tia}")
        print("конструкций: " + ", ".join(f"{k} {v}" for k, v in t.items()))
        print(f"вердикт: {data['c2s7']['verdict']}")
        e = data["effort"]
        print(f"трудоёмкость: P50 {e['p50_h']} ч, P90 {e['p90_h']} ч (модель, не калибрована)")
        for f in data["findings"]:
            o = f["origin"]
            print(
                f"  {f['outcome']:<10} {f['rule']:<22} {f['pou'] or '-':<24} {o['file']}:{o.get('line', '')}  {f.get('fragment', '')}"
            )
    return EXIT_FINDINGS if _fail(res, args.fail_on) else EXIT_OK


def cmd_migrate(args: argparse.Namespace) -> int:
    from c2s7.api import run_migrate

    opts = _options(args)
    out = Path(args.out)
    res = run_migrate(
        Path(args.input),
        out,
        opts,
        io_map=Path(args.io_map) if args.io_map else None,
        zip_path=Path(args.zip) if args.zip else None,
    )
    if args.bundle:
        from c2s7.emit.files import source_files, write_tia

        write_tia(out / "tia" / "sources" / "all.scl", "\n".join(t for _, t in source_files(res)))
    by, _ = res.collector.totals()
    n_src = sum(1 for b in res.blocks if b.kind != "ORGANIZATION_BLOCK")
    print(
        f"{TOOL}: {res.project.path} → {out}: блоков {n_src}, OB {len(res.obs)}, тегов {len(res.tags)}, "
        f"констант {len(res.constants)}; конструкций " + ", ".join(f"{k} {v}" for k, v in by.items() if v)
    )
    return EXIT_FINDINGS if _fail(res, args.fail_on) else EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    from c2s7.verify.run import verify

    return verify(Path(args.out), args)


def cmd_explain(args: argparse.Namespace) -> int:
    reg = registry()
    rid = args.rule.upper()
    if rid not in reg:
        print(f"нет правила {args.rule}; есть: {', '.join(sorted(reg))}", file=sys.stderr)
        return EXIT_INPUT
    r = reg[rid]
    mn, mode, mx = r.effort
    print(f"{r.id} — {r.title}\nкласс: {r.outcome}\n\n{r.why}\n\nчто делать: {r.fix}\nисточник: {r.source}")
    print(f"минуты на находку (модель, не калибрована): min {mn:g}, mode {mode:g}, max {mx:g}")
    return EXIT_OK


def cmd_probe(args: argparse.Namespace) -> int:
    from c2s7.emit.probe import write_probe

    n = write_probe(Path(args.out))
    print(f"пробник: {n} конструкций → {Path(args.out) / 'probe'}")
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    from c2s7.render.cli import render_cli

    return render_cli(args)


def cmd_site(args: argparse.Namespace) -> int:
    from c2s7.site.build import build_site

    return build_site(Path(args.out), [Path(c) for c in args.cases] if args.cases else None)


COMMANDS = {
    "inventory": cmd_inventory,
    "analyze": cmd_analyze,
    "migrate": cmd_migrate,
    "verify": cmd_verify,
    "explain": cmd_explain,
    "probe": cmd_probe,
    "render": cmd_render,
    "site": cmd_site,
}


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.cmd](args)
    except (IngestError, ProfileError, StSyntaxError) as exc:
        print(f"c2s7: ошибка: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except Exception as exc:
        from c2s7.verify.s7conv_clone import CloneError

        if isinstance(exc, CloneError):
            print(f"c2s7: клон s7conv: {exc}", file=sys.stderr)
            return EXIT_INPUT
        raise


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
