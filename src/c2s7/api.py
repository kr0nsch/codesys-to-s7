"""Программный интерфейс c2s7: загрузка входа, перенос, запись результата."""

from __future__ import annotations

import shutil
from pathlib import Path

from c2s7.convert.core import Converter, Options, Result
from c2s7.ingest.common import IngestError
from c2s7.ingest.iomap import load_io_map
from c2s7.ingest.layout import load_layout, load_single_st
from c2s7.ingest.plcopen import load_plcopen
from c2s7.model import Project
from c2s7.profiles import load as load_profile


def load_input(path: Path, base: Path | None = None) -> Project:
    """PLCopen XML (.xml), ST-раскладка (каталог с src/POUs) или одиночный .st."""
    if not path.exists():
        raise IngestError(f"нет входа {path}")
    if path.is_dir():
        return load_layout(path, base or Path.cwd())
    if path.suffix.lower() == ".xml":
        return load_plcopen(path, base or Path.cwd())
    if path.suffix.lower() == ".st":
        return load_single_st(path, base or Path.cwd())
    raise IngestError(f"{path}: неизвестный вход (ожидается .xml, .st или каталог раскладки)")


def migrate(project: Project, options: Options) -> Result:
    profile = load_profile(options.cpu, options.tia)
    if options.graphics is None:
        options.graphics = "simaticml" if profile.simaticml else "scl"
    res = Converter(project, profile, options).run()
    if options.graphics == "simaticml":
        from c2s7.emit.simaticml import emit_simaticml

        res.simaticml = emit_simaticml(res)
    return res


def run_migrate(
    inp: Path, out: Path, options: Options, io_map: Path | None = None, zip_path: Path | None = None
) -> Result:
    proj = load_input(inp)
    if io_map is not None:
        options.io_map = load_io_map(io_map)
        proj.io_map = options.io_map
    res = migrate(proj, options)
    from c2s7.emit.files import write_all, write_zip

    if out.exists():
        shutil.rmtree(out)
    files = write_all(res, out)
    if zip_path is not None:
        write_zip(zip_path, out, files)
    return res
