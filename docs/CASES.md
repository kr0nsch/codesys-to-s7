# Кейсы

## Кейс 1. Кольцо S7 → CODESYS → S7

**Вход.** Выход `s7conv convert samples/scl` проекта s7-to-codesys @
`2285760c1c99ce4218d5356c75e93111828f8e3b` (MIT): `tests/fixtures/s7-to-codesys/` — `src/` (19 POU +
S7Compat 7 + GVL 7 + DUT 7), `scenarios/` (6 наборов, 39 сценариев, 263 строки), `tasks.json`,
`tools/codesys/config.json`, LICENSE и `ATTRIBUTION.md`.

**Путь.** `c2s7 migrate tests/fixtures/s7-to-codesys --out out/ring` → `tia/sources/*` →
`s7conv convert <файлы списком> --tags roundtrip/PlcTags.csv --ob-config roundtrip/ob_config.json
--timers s7compat --emit-support` (клон `.cache/s7-to-codesys@2285760c`) → разбор s7conv обеих
сторон → нормализованное сравнение AST с исходным `samples/scl` клона.

**Распознавание S7Compat** (по MAPPING s7conv): `FB_S7Ton/Tof/Tp → TON_TIME/TOF_TIME/TP_TIME`,
`FB_S7FTrig → F_TRIG`, `F_NormX/F_ScaleX → NORM_X/SCALE_X`; `GVL_InstanceDBs` → экземплярные DB,
`GVL_IO`/`GVL_Markers` → теги с обратным пересчётом адресов, `ST_DB_*` → структура DB; PRG_* →
тела OB по `sources: "… (OBn)"` из `tasks.json`.

**Нормализация AST** (`c2s7.verify.astcmp.NORM_RULES`): `norm.comments`, `norm.header` (атрибуты и
порядок шапки), `norm.region`, `norm.case` (регистр имён), `norm.literal` (запись литералов),
`norm.db_init` (начальные значения DB по значению), `norm.addr_tag` (адрес ↔ имя тега),
`norm.sections`, `norm.string_default`, `norm.empty`.

**Результат** (`pytest tests/ring`, `c2s7 verify out/ring --roundtrip`):

| Вид | Совпало | Ожидание ТЗ |
|---|---|---|
| FUNCTION_BLOCK | 14/14 | 14/14 |
| FUNCTION | 1/1 | 1/1 |
| TYPE | 3/3 | 3/3 |
| DATA_BLOCK | 22/22 | 22/22 |
| ORGANIZATION_BLOCK | 3/4 | 4/4 (допустим `ring.lossy`) |

Число объектов на входе s7conv = числу файлов (44). Узлов `RawStmt/RawDecl` — 0. `bug` = 0,
`norm.*` = 0, `ring.lossy` = 2 → критерий MVP (`bug` = 0, `ring.lossy` ≤ 4) выполнен.

**Все расхождения `ring.lossy`:**

| № | Блок | Место | Правило | Причина |
|---|---|---|---|---|
| 1 | OB `Main` | тело, оператор 38: вызов `"DB_Logger"` | `ring.lossy.arg_dropped` | аргумент `extraInfo` типа Variant: s7conv не переносит Variant (MAPPING s7-to-codesys, «Не поддерживается»), оставляет `MIGRATION-TODO` и опускает аргумент; c2s7 восстанавливает закомментированный исходный вызов только как находку C2S7-RING-TODO |
| 2 | OB `Main` | тело, оператор 39: вызов `"DB_LegacyTlg"` | `ring.lossy.arg_dropped` | аргумент `source := P#M100.0 BYTE 16` типа Any — та же строка MAPPING |

Обе потери возникают на шаге S7 → CODESYS (s7conv), а не в c2s7: в ST CODESYS этих аргументов уже нет.
`MIGRATION-TODO` остаются manual (C2S7-RING-TODO в отчёте).

**Поведение** (R1, строка = вызов):

| Оракул | Сценарии | Строки |
|---|---|---|
| `c2s7.sim`, источник (ST CODESYS) | 39/39 | 263/263 |
| `c2s7.sim`, ST′ (обратный перевод нашего SCL) | 39/39 | 263/263 |
| stsim s7-to-codesys, ST′ + `gen-tests` | 39/39 тестов в 6 наборах | — |

| CODESYS Control Win 3.5.17.30, ST′ + coUnit из `s7conv gen-tests` (R1) | 39/39 тестов в 6 наборах | — |

R2 «фиксированный цикл» в Control Win: трассы источника (ST s7-to-codesys) и ST′ (`s7conv
--timers standard` из нашего SCL), по 6 блоков, 50 739 циклов каждая; c2s7.sim повторяет обе по
записанным отметкам времени без расхождений (487 точек сравнения на трассу). Трассы —
`tests/oracle/ring/`, тест — `tests/ring/test_ring_traces.py`.

## Кейс 2. Корпус «все языки» (ВОС «Заречная»)

Вымышленная фильтровальная станция; DSL — `corpus/<язык>/<кейс>/spec.py`, общие объекты —
`corpus/common.py`, вход демо — `corpus/zarechnaya.xml` (все 13 POU + GVL, DUT, обвязка).

| POU | Язык | Что проверяет | Цель c2s7 | Классы (S7-1500) |
|---|---|---|---|---|
| F_Convert | ST | REAL_TO_INT на половине, перенос, деление на 0, MUX, LIMIT при MN > MX | SCL | verify: ROUND, LIMIT, MUX, DIV0 |
| FB_Latch | ST | SR/RS при SET = RESET = 1, CTU/CTD, R/F_TRIG | SCL + CDS_SR/CDS_RS | review: SRRS, CTR |
| FB_TimeIdioms | ST | самосбрасывающийся таймер, чтение Q до вызова, TIME > 24 сут | SCL | review: TIMER-Q, TYPE-TIME |
| FB_LevelAlarm | FBD | 4 сети, Jump/Label, отрицание входа | FlgNet FBD | auto |
| FB_ValveCmd | FBD | MOVE/SEL/LIMIT (без EN/ENO — M0: N) | SCL (SEL/LIMIT вне подмножества FlgNet) | review: GFX-SCL; verify: SEM-LIMIT |
| PRG_Permissives | LD | P/N, S/R, инверсная катушка | FlgNet LAD + FB/DB | review: GFX-EDGE, POU-PRG |
| PRG_PumpInterlock | LD | параллели, двойная катушка | FlgNet LAD + FB/DB | verify: GFX-DOUBLECOIL; review: POU-PRG |
| FB_PiCfc | CFC | обратная связь (ADD сам на себя) | SCL | review: CFCFB; verify: SEM-LIMIT |
| FB_RatioCfc | CFC | две страницы, выход читается раньше шага | SCL | review: CFCFB |
| PRG_Backwash | SFC | таймауты шагов, N/S/R/P | SCL-автомат + FB/DB | review: GFX-SFC, ACT, POU-PRG |
| PRG_FilterAlt | SFC | альтернатива, приоритет переходов, прыжок | SCL-автомат + FB/DB | review: GFX-SFC, ACT, POU-PRG |
| FB_PulseCountIL | IL | JMPC назад → REPEAT | SCL | review: IL |
| F_ScaleIL | IL | CAL, CR через ST, ФБ в функции | SCL | manual: POU-FBINFC; review: IL, SEM-TEMP |

Классы по всему корпусу (S7-1500/V21): auto 385, review 35, verify 6, manual 4, impossible 0
(manual — нет `--io-map`, наложение `%MW10`/`%MX20.3`, UNION, ФБ в функции; уровень проекта ещё даёт
review TYPE-ALIAS/ENUM/RANGE, ADDR-MAP, RET — отчёт `migrate`).

**CODESYS.** 11 POU (без IL — M0: N) приняты `import_xml`, сборка 0 ошибок, экспорт
`source.cds.xml` семантически совпадает со `spec.py` (сети, порядок, отрицания, квалификаторы,
`executionOrderId`, понижение в ST) — `tools/corpus/build_corpus.py`, `tests/langs`.

**Эквивалентность** (`tools/corpus/corpus_check.py`, `tests/langs/test_corpus.py`), оба профиля:

| Проверка | Итог |
|---|---|
| R1: c2s7.sim(экспорт CODESYS) против сценариев эталонных моделей | 13/13 POU, 29/29 сценариев |
| R1: c2s7.sim(выход c2s7) — SCL → s7conv → ST′ или FlgNet → reader | 13/13 POU, 29/29 сценариев, S7-1500/V21 и S7-1200/V19 |
| R2: трассы Control Win (11 POU, 2227 циклов) против c2s7.sim(экспорт) | 2227/2227 |
| R2: те же трассы против c2s7.sim(выход c2s7) | 2227/2227 |

Трассы — `corpus/<язык>/<кейс>/oracle-codesys.{csv,json}` (формат `oracle-codesys/1`).
Блоки LAD/FBD проверены обратным чтением своего SimaticML — это самосогласованность.

## Кейсы 3–4

plc-process-lib и чужие экспорты — P1, в эту версию не входят (`docs/ROADMAP.md`).
