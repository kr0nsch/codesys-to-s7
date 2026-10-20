# Отчёт о проверках

Прогоны 20.10.2026 на машине автора: Windows 11, Python 3.12, CODESYS V3.5 SP17 Patch 3 (3.5.17.30,
сборка ОВЕН) с CODESYS Control Win V3 (`4096 / 0000 0001 / 3.5.17.30`, пользовательский процесс,
демо-режим), coUnit 1.2.0.0. TIA Portal и PLCSIM нет — проверок в TIA в этом отчёте нет.

## Без CODESYS (то же в CI)

```
python -m ruff check . && python -m ruff format --check . && python -m mypy
python -m pytest --cov=c2s7 --cov-branch --cov-report=json:build/coverage.json
python tools/check_coverage.py build/coverage.json
```

| Проверка | Итог |
|---|---|
| ruff, ruff format, mypy --strict (77 файлов) | без замечаний |
| pytest | 273 прошли, 5 пропущены (`-m codesys`) |
| покрытие всего | строки 90,2 %, ветви 80,2 % (порог 85/75) |
| `c2s7/emit/simaticml` | строки 89,7 %, ветви 78,7 % |
| `c2s7/sim` | строки 85,4 %, ветви 75,9 % |

Что входит в pytest:

- грамматика и печать ST/SCL (в том числе hypothesis: печать → разбор, 300 примеров), профили, задачи
  и приоритеты OB, адреса;
- реестр правил: у каждого из 57 правил — корпус `tests/corpus/C2S7-*/{pos,neg}`, описание, источник;
  обратные правила ко всем строкам «авто» MAPPING s7-to-codesys @ 2285760c;
- понижения IL/LD/FBD/CFC/SFC, свёртка переходов; FlgNet: свой валидатор (10 правил, у каждого негатив),
  XSD V19/V21 по фрагментам, golden `tests/golden/tia`, обратное чтение;
- свойства (hypothesis, 300 примеров, seed 20261019): `jumps.py` сохраняет трассу; случайные сети LD →
  FlgNet → reader — та же таблица истинности, что у понижения; автомат SFC = модель порядка цикла;
- кейс 1 (кольцо) и кейс 2 (корпус) — ниже; сайт, CLI, схемы SVG, детерминизм zip и `.xlsx`.

## Кейс 1 — кольцо S7 → CODESYS → S7

| Проверка | Итог |
|---|---|
| объектов на входе s7conv = файлов `tia/sources` + compat + OB | 44 = 44 |
| разбор s7conv без RawStmt/RawDecl | 0 узлов Raw |
| AST по видам (FB, FC, TYPE, DB, OB) | 14/14, 1/1, 3/3, 22/22, 3/4 |
| категории расхождений | bug 0, norm 0, ring.lossy 2 (`CASES.md`) → критерий MVP выполнен |
| R1 в c2s7.sim: источник / ST′ | 39/39 / 39/39 сценариев, 263/263 строки |
| R1 в stsim s7-to-codesys (ST′ + gen-tests) | 39/39 тестов в 6 наборах |
| **R1 в CODESYS Control Win** (ST′ + coUnit из gen-tests, `tools/codesys/ring_controlwin.py`) | **39/39**, сборка 0 ошибок, 0 предупреждений |
| **R2 в Control Win**: трасса источника против c2s7.sim | 50 739 циклов, 487 точек сравнения — без расхождений |
| **R2 в Control Win**: трасса ST′ (`s7conv --timers standard`) против c2s7.sim | 50 739 циклов, 487 точек — без расхождений |

## Кейс 2 — корпус «все языки» (ВОС «Заречная»)

| Проверка | Итог |
|---|---|
| CODESYS: `import_xml` → сборка → `export_xml` (`tools/corpus/build_corpus.py`) | 11 POU (IL — M0: N), 0 ошибок, 1 предупреждение C244 |
| семантика экспорта = `spec.py` | 11/11 |
| R1, c2s7.sim(экспорт) против сценариев эталонных моделей | 29/29 сценариев |
| R1, c2s7.sim(выход c2s7), S7-1500/V21 и S7-1200/V19 | 29/29 на обоих профилях |
| **R2, трассы Control Win** против c2s7.sim(экспорт) и c2s7.sim(выход c2s7) | 2227/2227 и 2227/2227 циклов |
| контрольные точки моделей, посчитанные вручную (`scenarios/reference/test_models.py`) | 18/18 |

## CodesysCompat в Control Win

CDS_SR/CDS_RS (обратный перевод s7conv нашего SCL) против Standard.SR/RS, 12 шагов с SET = RESET = 1
из обоих состояний (`tools/codesys/check_compat.py`): **совпали оба**.

## `pytest -m codesys`

```
python -m pytest -m codesys tests/codesys
```

5 тестов (пробы M0 ×2, сборка корпуса с семантическим сравнением, CDS_SR/RS, кольцо R1 в Control Win) —
5 прошли, 10 мин 41 с. Трассы R2 снимаются отдельно (`python tools/codesys/trace.py corpus|ring`) и
коммитятся; их сравнение с c2s7.sim идёт в обычном pytest.

## Что эти проверки не доказывают

- импорт и компиляцию в TIA Portal (не проверены — `HARDWARE_VALIDATION.md`);
- поведение на S7: кольцо показывает согласованность c2s7 и s7conv, общие ошибки одного автора могут
  погаситься; verify-конструкции — в `probe/`;
- LAD/FBD: обратное чтение своего SimaticML — самосогласованность, не независимая проверка.
