"""ST-раскладка plc-repo-template (контракт — docs/LAYOUT.md s7-to-codesys) и одиночный `.st`.

Раскладка: `src/POUs/**/<Имя>/<Имя>.decl.st` + `.impl.st`, методы `<M>.method.{decl,impl}.st`,
свойства `<P>.prop.decl.st` + `<P>.{get,set}.impl.st`, `src/GVLs/**/*.gvl.st` (`*.pvl.st` — список
Persistent Variables), `src/DUTs/**/*.dut.st`. Задачи — `tasks.json` рядом с `src/` (выход
`s7conv convert`) или `tools/codesys/config.json` (`modes.normal.tasks`).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from c2s7.ingest.common import IngestError, read_text, split_doc
from c2s7.model import Dut, Gvl, Origin, Pou, Project, Property, Task
from c2s7.pathsort import sorted_paths
from c2s7.st import nodes as A
from c2s7.st import parser as P


def tree_sha256(root: Path, files: list[Path]) -> str:
    """SHA-256 набора файлов: путь относительно корня + содержимое, по порядку путей."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(f.relative_to(root).as_posix().encode("utf-8") + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def find_src(root: Path) -> Path:
    """Каталог раскладки: `<root>/src` или сам root, если в нём POUs/GVLs/DUTs."""
    if (root / "src").is_dir() and any((root / "src" / d).is_dir() for d in ("POUs", "GVLs", "DUTs")):
        return root / "src"
    if any((root / d).is_dir() for d in ("POUs", "GVLs", "DUTs")):
        return root
    raise IngestError(f"{root}: нет раскладки (src/POUs, src/GVLs, src/DUTs)")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_layout(root: Path, base: Path | None = None) -> Project:
    """Раскладка → Project. base — относительно чего писать пути происхождения."""
    root = root.resolve()
    src = find_src(root)
    base = (base or root).resolve()
    files = sorted_paths(p for p in src.rglob("*.st") if p.is_file())
    proj = Project(name=root.name, kind="st-layout", path=_rel(root, base), sha256=tree_sha256(root, files))
    pous_dir = src / "POUs"
    if pous_dir.is_dir():
        for decl in sorted_paths(pous_dir.rglob("*.decl.st")):
            stem = decl.name[: -len(".decl.st")]
            if "." in stem:
                continue  # метод/аксессор
            if decl.parent.name != stem:
                continue
            proj.pous.append(_load_pou(decl, src, base))
    for gvl in sorted_paths(src.rglob("*.gvl.st")) + sorted_paths(src.rglob("*.pvl.st")):
        text = read_text(gvl)
        name = gvl.name.split(".")[0]
        doc, _ = split_doc(text)
        parsed = P.parse_gvl(text, _rel(gvl, base))
        folder = list(gvl.parent.relative_to(src).parts[1:])
        proj.gvls.append(
            Gvl(name, parsed, Origin(_rel(gvl, base), 1), folder, persistent_list=gvl.name.endswith(".pvl.st"), doc=doc)
        )
    for dut in sorted_paths(src.rglob("*.dut.st")):
        text = read_text(dut)
        doc, _ = split_doc(text)
        tdecl = P.parse_type(text, _rel(dut, base))
        folder = list(dut.parent.relative_to(src).parts[1:])
        proj.duts.append(Dut(tdecl.name, tdecl, Origin(_rel(dut, base), 1), folder, doc))
    proj.tasks = load_tasks(root)
    proj.obs = load_ob_hints(root)
    proj.root = str(base)
    return proj


def load_ob_hints(root: Path) -> list[dict[str, object]]:
    """Поле `obs` tasks.json s7conv: имя, программа, номер и вид исходного OB."""
    tasks_json = root / "tasks.json"
    if not tasks_json.exists():
        return []
    data = json.loads(read_text(tasks_json))
    return [dict(o) for o in data.get("obs", [])]


def _load_pou(decl_path: Path, src: Path, base: Path) -> Pou:
    folder_dir = decl_path.parent
    name = folder_dir.name
    decl_text = read_text(decl_path)
    doc, _ = split_doc(decl_text)
    text = P.parse_pou(decl_text, _rel(decl_path, base))
    impl_path = folder_dir / f"{name}.impl.st"
    impl_origin = None
    if impl_path.exists():
        body, tail = P.parse_body(read_text(impl_path), _rel(impl_path, base))
        text.body = body
        text.tail = tail
        impl_origin = Origin(_rel(impl_path, base), 1)
    kind = text.header.kind
    pou = Pou(
        name=text.header.name,
        kind=kind,
        language="ST",
        text=text,
        origin=Origin(_rel(decl_path, base), 1),
        folder=list(folder_dir.parent.relative_to(src).parts[1:]),
        doc=doc,
        impl_origin=impl_origin,
    )
    for mdecl in sorted_paths(folder_dir.glob("*.method.decl.st")):
        mname = mdecl.name[: -len(".method.decl.st")]
        mtext = P.parse_pou(read_text(mdecl), _rel(mdecl, base))
        mimpl = folder_dir / f"{mname}.method.impl.st"
        if mimpl.exists():
            mtext.body, mtext.tail = P.parse_body(read_text(mimpl), _rel(mimpl, base))
        pou.methods.append(mtext)
    for pdecl in sorted_paths(folder_dir.glob("*.prop.decl.st")):
        pname = pdecl.name[: -len(".prop.decl.st")]
        ptext = P.parse_pou(read_text(pdecl), _rel(pdecl, base))
        prop = Property(pname, ptext.header.return_type or A.NamedType("INT"))
        for acc in ("get", "set"):
            impl = folder_dir / f"{pname}.{acc}.impl.st"
            if impl.exists():
                body, _ = P.parse_body(read_text(impl), _rel(impl, base))
                if acc == "get":
                    prop.get_body = body
                else:
                    prop.set_body = body
        pou.properties.append(prop)
    return pou


def load_tasks(root: Path) -> list[Task]:
    """Задачи из tasks.json (s7conv) или tools/codesys/config.json (modes.normal.tasks)."""
    tasks_json = root / "tasks.json"
    config = root / "tools" / "codesys" / "config.json"
    raw: list[dict[str, object]] = []
    if tasks_json.exists():
        data = json.loads(read_text(tasks_json))
        raw = list(data.get("tasks", []))
    elif config.exists():
        data = json.loads(read_text(config))
        raw = list(data.get("modes", {}).get("normal", {}).get("tasks", []))
    out: list[Task] = []
    for t in raw:
        kind = str(t.get("type") or t.get("kind") or "cyclic")
        interval = t.get("interval_ms")
        prio = t.get("priority")
        out.append(
            Task(
                name=str(t["name"]),
                kind=kind,
                interval_ms=float(str(interval)) if interval is not None else None,
                priority=int(str(prio)) if prio is not None else 1,
                pous=[str(p) for p in t.get("pous", [])],  # type: ignore[attr-defined]
                sources=[str(s) for s in t.get("sources", [])],  # type: ignore[attr-defined]
            )
        )
    return out


_HEADER = re.compile(r"^\s*(PROGRAM|FUNCTION_BLOCK|FUNCTION|TYPE|VAR_GLOBAL|INTERFACE)\b", re.IGNORECASE | re.MULTILINE)


def load_single_st(path: Path, base: Path | None = None) -> Project:
    """Одиночный `.st` с одним или несколькими объектами (TYPE..END_TYPE, POU..END_*, VAR_GLOBAL)."""
    path = path.resolve()
    base = (base or path.parent).resolve()
    text = read_text(path)
    rel = _rel(path, base)
    proj = Project(
        name=path.stem,
        kind="st",
        path=rel,
        sha256=hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest(),
    )
    for chunk, line in _split_objects(text):
        head = chunk.lstrip()
        first = _HEADER.search(chunk)
        word = first.group(1).upper() if first else ""
        if word == "TYPE":
            decl = P.parse_type(chunk, rel)
            proj.duts.append(Dut(decl.name, decl, Origin(rel, line)))
        elif word == "VAR_GLOBAL":
            gname = path.stem if not proj.gvls else f"{path.stem}_{len(proj.gvls) + 1}"
            proj.gvls.append(Gvl(gname, P.parse_gvl(chunk, rel), Origin(rel, line)))
        elif head:
            doc, _ = split_doc(chunk)
            pt = P.parse_pou(chunk, rel)
            proj.pous.append(Pou(pt.header.name, pt.header.kind, "ST", pt, Origin(rel, line), doc=doc))
    return proj


_HEAD = re.compile(
    r"^[ \t]*(PROGRAM|FUNCTION_BLOCK|FUNCTION|TYPE|INTERFACE|VAR_GLOBAL)\b", re.IGNORECASE | re.MULTILINE
)
_END = re.compile(r"\b(END_PROGRAM|END_FUNCTION_BLOCK|END_FUNCTION|END_TYPE|END_INTERFACE)\b", re.IGNORECASE)


def _split_objects(text: str) -> list[tuple[str, int]]:
    """Режет файл на объекты: POU/TYPE — до END_*, блоки VAR_GLOBAL подряд — один GVL.

    Прагмы и комментарии перед заголовком остаются с объектом (начало объекта — конец предыдущего).
    """
    clean, _ = P.strip_comments(text)
    out: list[tuple[str, int]] = []
    pos = 0
    start = 0
    n = len(clean)
    while pos < n:
        m = _HEAD.search(clean, pos)
        if m is None:
            break
        word = m.group(1).upper()
        if word == "VAR_GLOBAL":
            end = m.start()
            while True:
                e = re.search(r"\bEND_VAR\b", clean[end:], re.IGNORECASE)
                if e is None:
                    end = n
                    break
                end = end + e.end()
                nxt = _HEAD.search(clean, end)
                if nxt is None or nxt.group(1).upper() != "VAR_GLOBAL" or clean[end : nxt.start()].strip():
                    break
                end = nxt.start()
        else:
            e = _END.search(clean, m.end())
            end = e.end() if e else n
            semi = clean.find(";", end)
            if semi != -1 and not clean[end:semi].strip():
                end = semi + 1
        out.append((text[start:end], text.count("\n", 0, start) + 1))
        start = pos = end
    rest = text[start:]
    if P.strip_comments(rest)[0].strip():
        out.append((rest, text.count("\n", 0, start) + 1))
    return out
