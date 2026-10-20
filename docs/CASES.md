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

R1/R2 в CODESYS Control Win — `docs/TEST_REPORT.md`.

## Кейс 2. Корпус «все языки» (ВОС «Заречная»)

13 POU на шести языках, собраны в CODESYS 3.5.17.30 и выгружены как эталон `source.cds.xml`.
Описание, классы конструкций и эквивалентность — раздел ниже (этап C).

## Кейсы 3–4

plc-process-lib и чужие экспорты — P1, в эту версию не входят (`docs/ROADMAP.md`).
