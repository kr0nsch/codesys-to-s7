"""Пакет устанавливается и отвечает версией."""

from __future__ import annotations

import pytest

import c2s7
from c2s7 import cli


def test_version() -> None:
    assert c2s7.__version__ == "0.1.0"
    assert c2s7.TOOL == "c2s7 0.1.0"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "c2s7 0.1.0" in capsys.readouterr().out
