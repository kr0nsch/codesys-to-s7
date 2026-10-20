# Формат выхода для TIA Portal

Что пишет `c2s7 migrate` в `out/<имя>/tia/` и почему так. TIA Portal у автора не установлен:
форма файлов взята из опубликованных экспортов (корпус s7-to-codesys, эталонный набор FlgNet,
XSD V19/V21) и проверяется разбором s7conv, XSD и своим валидатором. Импорт в TIA — процедура
`docs/HARDWARE_VALIDATION.md`, не доказательство.

## Внешние исходники `tia/sources/`

- Один объект на файл: `NNN_<Имя>.udt` (PLC data type), `.db` (глобальный или экземплярный DB),
  `.scl` (FC/FB). Префикс `NNN` задаёт порядок импорта: типы → глобальные DB → FC/FB →
  экземплярные DB.
- UTF-8 с BOM, концы строк CRLF (так пишет TIA при экспорте; проверка — `tests/unit/test_emit_ingest.py`).
- Первая строка — комментарий `// создано c2s7 0.1.0 · источник <путь> · SHA-256 <хеш входа>`.
- Шапка блока: имя → `TITLE` → `{ S7_Optimized_Access := 'TRUE' }` → `AUTHOR`/`FAMILY` (если есть) →
  `VERSION : 0.1`. Члены-экземпляры системных ФБ — с атрибутами
  `{InstructionName := 'TON_TIME'; LibVersion := '1.0'}`, как в экспортах.
- **OB в исходники не пишутся.** Тип, номер и период OB внешний исходник не задаёт, а OB1 из
  исходника конфликтует с автоматически созданным и откатывает импорт. Тела OB — в
  `tia/ob/OB_<Задача>.body.scl`, план OB и приоритеты — `roundtrip/TASKS.md`; OB создаёт человек.
  Для кольца те же тела лежат полными блоками в `roundtrip/ob/` (их читает только s7conv).
- `--bundle` добавляет `all.scl` — все объекты в порядке номеров.

## Разбор s7conv: закрытый список исключений

Все файлы `.scl/.db/.udt` выхода разбираются s7conv (клон @ `2285760c`) без `RawStmt`, `RawDecl` и
`RawBlock`. Тест: `tests/ring/test_ring.py::test_ring_ast_categories` (`raw == []`), функция
`c2s7.verify.astcmp.raw_nodes`. Исключения — только из этого списка; каждое считается в отчёте
своим правилом и исключается из кольцевого сравнения:

| Конструкция | Когда появляется | Правило |
|---|---|---|
| `GOTO`/метка в SCL | прыжок в графике, который `lower/jumps.py` не свёл к структурному коду | C2S7-GFX-GOTO |
| `REF_TO`, `VARIANT`, `DB_ANY` | заготовка под ручную доработку для POINTER/REFERENCE/`__NEW` | C2S7-TYPE-PTR, C2S7-PROF-REF |
| строки `MIGRATION-TODO` s7conv, восстановленные в кольце | исходник S7 уже содержал конструкцию без аналога | C2S7-RING-TODO |

## Теги `tia/tags/PLCTags.xlsx`

Лист «PLC Tags»: Name, Path, Data Type, Logical Address, Comment, Hmi Visible, Hmi Accessible,
Hmi Writeable, Typeobject ID, Version ID (колонки экспорта редактора тегов). Лист «User Constants»:
Name, Path, Data Type, Value, Comment. Импорт — через GUI TIA (сверка колонок — в
`HARDWARE_VALIDATION.md`). Файл детерминирован: фиксированные свойства книги (`created`/`modified`),
записи без сжатия с датой 1980-01-01.

Адреса: `%IXa.b → %Ia.b` при байтовой адресации битов CODESYS (по пробе M0), `%IWn → %IW(2n)`,
`%IDn → %ID(4n)`; пословные биты — manual. Порядок байтов CODESYS (little-endian) и S7 (big-endian)
различается: наложения разной ширины — C2S7-ADDR-OVERLAP.

## Файлы для кольца `roundtrip/`

`PlcTags.csv`, `ob_config.json`, `BlockProperties.csv` — в форматах s7conv (их читает
`s7conv convert --tags --ob-config`); `TASKS.md`, `IO_MAP.csv`, `MANUAL_STEPS.md` — для человека.

## SimaticML `tia/simaticml/`

Блоки LD/FBD — FlgNet (`Document/Engineering version` по `--tia V19|V21`). Подробности формата,
UId и проверка XSD — раздел «FlgNet» ниже (этап B).

## Детерминизм

Одинаковый вход даёт одинаковые байты: порядок объектов и находок фиксирован, дат и путей машины в
файлах нет. `--zip` пишет `ZIP_STORED`, имена по порядку, дата 1980-01-01, атрибуты 0644
(`00-INDEX.md` §4.10). Тест — `tests/unit/test_emit_ingest.py::test_zip_deterministic`.
