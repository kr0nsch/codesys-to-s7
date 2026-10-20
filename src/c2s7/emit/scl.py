"""Печать блоков S7 во внешний исходник (`.scl`, `.db`, `.udt`) в форме экспорта TIA Portal.

Шапка блока: имя → TITLE → { S7_Optimized_Access := 'TRUE' } → AUTHOR/FAMILY → VERSION; секции —
с отступом 3/6 пробелов, тело — с табуляцией, как в экспортах TIA (codesys-to-s7.md R§3). Файл —
UTF-8 с BOM и CRLF (запись — c2s7.emit.files).
"""

from __future__ import annotations

from c2s7.emit.printer import Printer, scl_name
from c2s7.s7 import S7Block, S7Member, S7Section


def _attrs(attrs: dict[str, str]) -> str:
    if not attrs:
        return ""
    return " {" + "; ".join(f"{k} := '{v}'" for k, v in attrs.items()) + "}"


def member_lines(m: S7Member, indent: str) -> list[str]:
    if m.raw is not None:
        return [indent + line for line in m.raw.splitlines()]
    name = scl_name(m.name)
    comment = f"   // {m.comment}" if m.comment else ""
    if m.struct is not None:
        out = [f"{indent}{name}{_attrs(m.attrs)} : {m.type or 'Struct'}{comment}"]
        for sub in m.struct:
            out.extend(member_lines(sub, indent + "   "))
        out.append(f"{indent}END_STRUCT;")
        return out
    init = f" := {m.init}" if m.init is not None else ""
    return [f"{indent}{name}{_attrs(m.attrs)} : {m.type}{init};{comment}"]


def section_lines(sec: S7Section) -> list[str]:
    out = [f"   {sec.header} "]
    for m in sec.members:
        out.extend(member_lines(m, "      "))
    out.append("   END_VAR")
    out.append("")
    return out


def header_comment(tool: str, source: str, sha: str) -> str:
    return f"// создано {tool} · источник {source} · SHA-256 {sha}"


def block_text(b: S7Block, head: str = "") -> str:
    p = Printer("scl", indent="\t")
    lines: list[str] = []
    if head:
        lines.append(head)
    kw = b.kind
    name = f'"{b.name}"'
    if kw == "FUNCTION":
        lines.append(f"FUNCTION {name} : {b.return_type or 'Void'}")
    else:
        lines.append(f"{kw} {name}")
    if b.title and kw != "TYPE":
        lines.append(f"TITLE = {b.title}")
    if kw != "TYPE":
        lines.append("{ S7_Optimized_Access := '" + ("TRUE" if b.optimized else "FALSE") + "' }")
    if b.author:
        lines.append(f"AUTHOR : {b.author}")
    if b.family:
        lines.append(f"FAMILY : {b.family}")
    lines.append(f"VERSION : {b.version}")
    if kw == "DATA_BLOCK" and b.non_retain:
        lines.append("NON_RETAIN")
    for c in b.comment:
        lines.append(f"//{c}")
    if kw == "TYPE":
        lines.append("   STRUCT ")
        for m in b.struct:
            lines.extend(member_lines(m, "      "))
        lines.append("   END_STRUCT;")
        lines.append("")
        lines.append("END_TYPE")
        return "\n".join(lines) + "\n"
    if kw == "DATA_BLOCK":
        if b.db_of:
            lines.append(b.db_of)
        for sec in b.sections:
            lines.extend(section_lines(sec))
        lines.append("")
        lines.append("BEGIN")
        begin = list(b.db_begin)
        for sec in b.sections:
            for m in sec.members:
                begin.extend((f"{scl_name(m.name)}{rel}", v) for rel, v in m.begin)
        for path, value in begin:
            lines.append(f"   {path} := {value};")
        lines.append("")
        lines.append("END_DATA_BLOCK")
        return "\n".join(lines) + "\n"
    for sec in b.sections:
        lines.extend(section_lines(sec))
    lines.append("")
    lines.append("BEGIN")
    lines.extend(p.stmts(b.body, 1))
    lines.append(f"END_{kw}")
    return "\n".join(lines) + "\n"
