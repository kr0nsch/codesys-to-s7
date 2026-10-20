"""Профили цели (CPU и версия TIA) — данные с источниками, `profiles/*.yaml`."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

CPUS = ("s7-1200", "s7-1500")
TIA_P0 = ("V19", "V21")


class ProfileError(ValueError):
    """Неизвестный CPU или версия TIA (код CLI 2)."""


@functools.cache
def _load(name: str) -> dict[str, Any]:
    text = resources.files("c2s7.profiles").joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    return data


@dataclass(frozen=True)
class Profile:
    cpu: str
    tia: str
    data: dict[str, Any]
    tia_data: dict[str, Any]

    @property
    def title(self) -> str:
        return str(self.data["title"])

    def language(self, lang: str) -> bool:
        return bool(self.data["languages"][lang]["supported"])

    def type_supported(self, s7type: str) -> bool:
        info = self.data["types"].get(s7type)
        return True if info is None else bool(info["supported"])

    def type_source(self, s7type: str) -> str:
        info = self.data["types"].get(s7type) or {}
        key = info.get("source", "")
        return str(self.data["sources"].get(key, key))

    @property
    def ob(self) -> dict[str, Any]:
        ob: dict[str, Any] = self.data["ob"]
        return ob

    def source(self, key: str) -> str:
        return str(self.data["sources"].get(key, key))

    def namespace(self, kind: str) -> str:
        v = str(self.tia_data["versions"][self.tia][kind]).split("+")[-1]
        return str(self.tia_data["namespaces"][kind]).format(v=v)

    @property
    def simaticml(self) -> bool:
        return bool(self.tia_data["versions"][self.tia].get("simaticml"))


def tia_table() -> dict[str, Any]:
    return _load("tia")


def load(cpu: str, tia: str = "V21") -> Profile:
    if cpu not in CPUS:
        raise ProfileError(f"неизвестный CPU {cpu!r}: допустимы {', '.join(CPUS)} (S7-1200 G2 не поддерживается)")
    tdata = tia_table()
    versions = tdata["versions"]
    if tia not in versions:
        raise ProfileError(f"неизвестная версия TIA {tia!r}: {', '.join(versions)}")
    if versions[tia].get("status") == "excluded":
        raise ProfileError(f"TIA {tia} исключена: {' '.join(str(versions[tia].get('reason', '')).split())}")
    return Profile(cpu, tia, _load(cpu), tdata)
