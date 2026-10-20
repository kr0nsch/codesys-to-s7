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

## SimaticML `tia/simaticml/` (FlgNet)

POU на LD и FBD при `--tia V19|V21` (умолчание `--graphics simaticml`) выдаются документами
SimaticML: `Document` → `Engineering version` → `SW.Blocks.FB|FC` с интерфейсом
(`Sections`, пространство имён `Interface/v5`) и сетями `SW.Blocks.CompileUnit` с `FlgNet`
(`NetworkSource/FlgNet/v5`). Такой блок в `tia/sources/` не попадает. Через GUI TIA SimaticML не
импортируется — только Openness (у автора не проверено; процедура — `HARDWARE_VALIDATION.md`).

**Закрытое подмножество** (реестр `src/c2s7/emit/simaticml/parts.py`, у каждой части — источник):

| Часть | LAD/FBD | Источник |
|---|---|---|
| `Contact` (+ `Negated operand` — НЗ), `Coil`, `SCoil`, `RCoil`, `Not`, `O` (Card), `PBox` | LAD | эталонный набор bulaofen @ e131b257 [M] |
| `Gt/Ge/Lt/Le/Eq/Ne` (SrcType), `Add/Sub/Mul/Div/Mod` (SrcType, Card), `Move` (Card), `TON` (Version 1.0, Instance, time_type) | оба | эталонный набор |
| `NBox`, `TOF`, `TP` | оба | по аналогии с `PBox`/`TON` |
| `A`, `X` (Card) | FBD | имена — реестр s7-lint-vscode @ 0735f8ff (FBD-bit-logic), форма — по `O` |
| `Jump` + `Access Scope="Label"`, `Labels/LabelDeclaration` | оба | по схеме LADFBD_v5, **эталона нет** |

Отображение: контакт P/N → `Contact` + `PBox`/`NBox` с битом памяти в статике (тот же бит, что в
SCL-пути; только для ветви от шины); параллель → `O`; общие элементы сети строятся один раз
(провод с несколькими приёмниками); инверсная катушка → `Not` + `Coil`; в FBD отрицание NOT уходит
в `Negated` входа приёмника, логический результат пишется через `Coil`, числовой выход бокса —
проводом прямо на операнд. Всё остальное (SEL, LIMIT, вызовы своих ФБ, CTU, EN/ENO, RETURN,
массивы и т. д.) — блок целиком в SCL с находкой C2S7-GFX-SCL.

**Детерминизм.** UId — по обходу, с 21 в каждой сети (провода — после частей), ID объектов —
шестнадцатеричный счётчик, `DocumentInfo/Created` — фиксированная метка `2026-10-19T00:00:00Z`
(не время экспорта TIA). `AutoNumber` = true, `Number` — порядковый. Тексты (`MultilingualText`) —
культура `en-US` (есть в любой установке TIA), текст — как в CODESYS. `Namespace` — только V21.

**Проверки.** Свой валидатор (`validate.py`, всегда; правила V-ENG, V-UID, V-REF, V-PIN, V-ONCE,
V-PART, V-TEMPLATE, V-VERSION, V-REACH, V-SCOPE, у каждого — негатив в `tests/formats`), XSD V19/V21
по фрагментам `FlgNet` и `Sections` (job `xsd`, XSD скачиваются `tools/fetch_xsd.py` по SHA-256),
обратное чтение `verify/s7xml_reader.py` → `c2s7.sim` против понижения источника (самосогласованность)
и golden `tests/golden/tia/*.xml`. Прохождение XSD подтверждением формата не считается: эталонный
набор слабый (V21, MIT, происхождение [M]), импорт в TIA не проверен.

## Детерминизм

Одинаковый вход даёт одинаковые байты: порядок объектов и находок фиксирован, дат и путей машины в
файлах нет. `--zip` пишет `ZIP_STORED`, имена по порядку, дата 1980-01-01, атрибуты 0644
(`00-INDEX.md` §4.10). Тест — `tests/unit/test_emit_ingest.py::test_zip_deterministic`.
