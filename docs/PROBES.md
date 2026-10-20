# Пробы M0 — что проверено до разборщиков

Прогоны 20.10.2026 на машине автора: CODESYS V3.5 SP17 Patch 3 (3.5.17.30, сборка ОВЕН, профиль
`CODESYS V3.5 SP17 Patch 3`), устройство CODESYS Control Win V3 (`4096 / 0000 0001 / 3.5.17.30`),
рантайм — пользовательский процесс CODESYSControlService (демо-режим). TIA Portal, PLCSIM и
SIMATIC AX нет ни у автора, ни у владельца — всё, что касается TIA, ниже названо прямо.

Воспроизведение:

```
python tools/probes/run_probes.py import        # импорт по языкам → сборка → экспорт (CODESYS)
python tools/probes/controlwin_probe.py         # поведение в Control Win (под блокировкой рантайма)
python -m pytest -m codesys tests/codesys       # те же пробы как тесты
```

Входы пробы строит DSL корпуса (`tools/corpus/builder.py`, POU — `tools/probes/probe_specs.py`);
экспорты CODESYS лежат в `tests/fixtures/sp17/` (MIT, сделаны на этой машине) и служат фикстурами
разборщика PLCopen.

## 1. Импорт PLCopen по языкам (CODESYS)

Критерий G/N: импорт без ошибок, сборка без ошибок (POU вызывается из задачи — `app.build()`
компилирует только достижимое), экспорт даёт тело того же языка с теми же элементами.

| Язык / форма | Итог | Что показала проба |
|---|---|---|
| ST | **G** | `application.import_xml(path)` создаёт POU; сборка 0 ошибок после ссылки на Standard (в новом проекте с Control Win библиотеки Standard нет — `add_placeholder("Standard", "Standard, * (System)")`) |
| FBD | **G** | 4 сети: GT, NOT → Jump, OR/AND с отрицанием входа, Label. Экспорт совпадает поэлементно; метка сети экспортируется перед заголовком сети. Атрибут `negated` у `<jump>` CODESYS отвергает («Атрибут "negated" не объявлен») — отрицание условия только блоком NOT |
| FBD, бокс с EN/ENO | **N** | `formalParameter="EN"/"ENO"` CODESYS читает как позиционные входы оператора; с ENO в списке выходов объект ломается («Internal error … providing language model information»). Форма EN/ENO в PLCopen не найдена ни в своих, ни в публичных экспортах |
| LD | **G** | контакты НО/НЗ, фронты P/N (`edge="rising/falling"`), катушки обычная/инверсная/S/R, параллельные ветви, несколько сетей. CODESYS экспортирует LD с одной левой шиной `localId="0"` и сквозной нумерацией; сеть начинается парой `comment` + `vendorElement networktitle`. Своя левая шина на сеть — элементы сети теряются |
| LD, бокс с EN/ENO | **N** | бокс в цепи принимается только для операторов сравнения («Элемент с EN может быть использован только с операторами сравнения»); MOVE с EN/ENO ломает объект |
| CFC | **G** | обратная связь (вход ADD от выхода LIMIT с большим `executionOrderId`) собирается. Провод CFC идёт через `<connector name="">`: от входной переменной — `formalParameter` = её выражение, от выхода оператора — `formalParameter=""`, от выхода ФБ — имя выхода; вход блока ссылается на connector без `formalParameter`. Входы операторов CODESYS переименовывает позиционно (`In1…InN`) |
| CFC со страницами | **G** | `<CFC page-oriented="true">` + `vendorElement` `cfcpage`; порядок выполнения не по документу сохраняется |
| SFC | **G** | шаги, начальный шаг, действие шага (атрибут `700a583f…`), блоки действий N/S/R/P, альтернатива, параллель, переход по `Шаг.t`, прыжок — экспорт совпадает поэлементно |
| SFC: entry/exit-действия | **N** | в публичных экспортах (CODESYS, TwinCAT) атрибута для entry/exit нет, скриптинг SFC не редактирует; форма неизвестна. В корпусе вместо entry/exit — действие шага и квалификатор P |
| IL | **N** | стандартный `<IL>` импорт молча пропускает: объект не создан, исключения нет (как в E§3.3). Опция «Enable IL» скриптингом не включается: в ScriptEngine 4.0 API настроек нет, а пользовательские настройки хранятся под GUID компонентов (`%APPDATA%\CODESYS\UserOptions-*\CODESYS.opt`) — править их вслепую не стали. Шаг владельца — в `HARDWARE_VALIDATION.md` |
| METHOD, PROPERTY, ACTION | **G** | методы и свойства — в addData `…/method`, `…/property` (Get/Set), действия — `<actions>` |
| GVL | **G** | AT `%IX/%MW/%MX/%MD` принимаются. RETAIN/PERSISTENT — через `MixedAttrsVarList`; **если в GVL с секцией PERSISTENT есть ещё и `interfaceasplaintext`, CODESYS создаёт список Persistent Variables, и все переменные становятся постоянными** — генератор корпуса для таких GVL текст объявления не пишет. AT и PERSISTENT в одном списке — ошибка «Прямое объявление адреса невозможно в Persistent-списке» |
| DUT | **G** | STRUCT с начальным значением, ENUM с базовым типом |
| Задачи | **G** (скриптингом) | `create_task_configuration`, `create_task`, `interval`, `priority`, `KindOfTask.Freewheeling`. В экспорте приложения — `task` (`interval="PT0.01S"`) и addData `tasksettings` (`KindOfTask`, `Interval`, `IntervalUnit`) |

Решения по языкам с N — в [FORMAT-CODESYS.md](FORMAT-CODESYS.md): IL разбирается из текста
(публичные экспорты и корпус без CODESYS), EN/ENO и entry/exit проверяются на собственном NetIR и
SfcIR, в CODESYS не импортируются.

Сбои, известные по форуму («The given key was not present in the dictionary» на ветвлениях,
путаница LD/LD2) на этих пробах не воспроизвелись; первоисточник форума не найден — пункт
остаётся [L].

## 2. Поведение в CODESYS Control Win

Программа `PRG_M0` за один цикл вычисляет значения, хост читает их `read_value`
(`build/probes/controlwin.json`). Рантайм уже работал (запущен другим проектом), использован без
перезапуска под общей блокировкой.

| Проверка | CODESYS 3.5.17.30 / Control Win | Следствие для c2s7 |
|---|---|---|
| `REAL_TO_INT(2.5)`, `(3.5)`, `(-2.5)`, `(-3.5)`, `(0.5)`, `(1.5)` | 3, 4, −3, −4, 1, 2 | половина округляется **от нуля**; `c2s7.sim` делает так же. stsim s7-to-codesys считает через `round()` Python (банковское округление: 2, 4, −2, −4, 0, 2) — расхождение stsim с Control Win, находка |
| `REAL_TO_DINT(2.5)` | 3 | то же |
| SR(SET1 = RESET = TRUE).Q1 | TRUE | SR CODESYS — установка доминирует = S7 RS → `CDS_SR` |
| RS(SET = RESET1 = TRUE).Q1 | FALSE | RS CODESYS — сброс доминирует = S7 SR → `CDS_RS` |
| CTU: 70 000 фронтов CU | CV = 65535, Q = TRUE | счётчик стоит на 65535 (без переноса) |
| CTD: LOAD PV = 2, затем 5 фронтов CD | CV = 0, Q = TRUE | стоит на нуле |
| `LIMIT(10, 5, 0)`, `LIMIT(10, 20, 0)` (MN > MX) | 0, 0 | результат = MX (`MIN(MAX(IN, MN), MX)`); S7 по сведениям s7-to-codesys даёт IN и ENO = FALSE — `verify`, пробник |
| VAR_OUTPUT функции `:= 7`, второй вызов без присваивания | 7 | выходы и локальные переменные FUNCTION инициализируются при каждом вызове → c2s7 пишет присваивания начальных значений в начало тела FC |
| F_TRIG, первый вызов с CLK = FALSE | Q = FALSE | как S7 — F_TRIG `auto` |
| `INT 32767 + 1` | −32768 | перенос по разрядности |
| `DINT := INT(300) * INT(300)` | 90 000 | промежуточный результат в 32 битах; в S7 — в типе операндов (Int) → C2S7-SEM-OVERFLOW |
| `T#0MS - T#1MS` | `T#49d17h2m47s295ms` | TIME без знака, перенос → C2S7-TYPE-TIME |
| `%MW0 := 16#0108`, читаем `%MX1.0`, `%MX0.3`, `%MB1` | TRUE, TRUE, 1 | **байтовая** адресация битов (`%MX1.0` — бит 0 байта 1), порядок байтов little-endian; умолчание `--cds-bit-addressing byte` |
| `%MW2 := 16#ABCD`, читаем `%MD1` | 43981 (16#ABCD) | `%MD1` = байты 4…7, `%MW2` = байты 4…5: номер в `%MW/%MD` — номер слова/двойного слова; в S7 — номер байта → `%MWn → %MW(2n)`, `%MDn → %MD(4n)` |
| `read_values` 200 значений INT | 0,24 с | ≈ 830 значений/с > 200 — трасса R2 читается массивами, без упаковки в STRING |

## 3. Форматы и внешние источники

| Пункт | Итог |
|---|---|
| XSD SimaticML | `tools/fetch_xsd.py` качает V19 и V21 из dotnetprojects/DotNetSiemensPLCToolBoxLibrary @ `bbe5becc…` с проверкой SHA-256 в `.cache/xsd/`. Матрица пространств имён (`--matrix`) совпадает с таблицей ТЗ: V19 и V21 — Interface v5, FlgNet v5, SCL v4, Graph v6, Access v5; V20 — v5/v4/v3/v5/v4 |
| Эталонный набор FlgNet (bulaofen0036-coder/TIA_Portal_Openness_MCP @ `e131b257…`, 4 файла `MCPVerify_F?_LAD*.xml`, MIT) | Признаков настоящего экспорта нет: у всех `Created` = `2026-05-11T00:00:00.0000000Z` (круглое время), `ExportSetting` = None, комментарии вида «MCP v3: … import+compile check». Атрибуты, которые пишет TIA (`DisabledENO`, `Version` у TON, `TemplateValue`), есть, но могли быть набраны вручную. Итог по правилу ТЗ: **FlgNet c2s7 «соответствует XSD и структуре набора, эталона нет»**; набор используется как [M] для топологии проводов и имён частей |
| eponce00/tiaopen-mcp @ `e2b26de4…`, `templates/lad`, `templates/fbd/fb-call.xml` | шаблоны с токенами, помечены «PENDING VERIFICATION» — только [M], в тестах не используются |
| truST @ `161992b5…`, судьба `VAR` программы | по коду (`crates/trust-plcopen/src/plcopen/export_helpers.rs`, `render_siemens_scl_pou`, стр. 57–89) экспорт `--target siemens` меняет только строку `PROGRAM X` на `ORGANIZATION_BLOCK "X"` и `END_PROGRAM`; секция `VAR` программы остаётся в теле OB как есть. У OB статики нет, поэтому состояние программы так не сохраняется — c2s7 переводит PROGRAM в FB + экземплярный DB |
| s7conv @ `2285760c` (клон `.cache/s7-to-codesys@2285760c`) | проверка SHA и пустого `git status` проходит; `convert` с явным списком файлов читает `.udt`/`.db` как SCL; `gen-tests` есть; `s7conv/tests/stsim.py` импортируется через `sys.path` |
| s7-lint headless, plc-code | не проверялись: оба — P1 (`extras.yml`), в MVP не входят (`ROADMAP.md`) |

## 4. Что показали корпус и трассы (после M0)

Прогоны 20.10.2026, та же машина и рантайм (Control Win запускался под общей блокировкой; рантайм,
запущенный другим проектом, не перезапускался — при истёкшем демо-режиме прогоны ждали его смены).

| Пункт | Итог | Следствие |
|---|---|---|
| Корпус «Заречная» в CODESYS (`tools/corpus/build_corpus.py`) | 11 POU приняты, сборка — 0 ошибок, 1 предупреждение (C244: в приложении нет списка VAR_PERSISTENT для `GVL_Retain.rFilterHours`); семантика экспорта = `spec.py` для всех 11 | экспорты — `corpus/<язык>/<кейс>/source.cds.xml` |
| UNION в PLCopen | схема tc6_0200 не знает `<union>` — `import_xml` падает | DUT создаются объектами с текстом объявления |
| SFC: ветви альтернативы, оканчивающиеся прыжком без схождения (форма `builder.py`) | `import_xml` молча пропустил POU и его действия | кейс `PRG_FilterAlt` перестроен на схождение с прыжком после него |
| Время шага SFC | трасса `PRG_Backwash` (R2): переход по `Drain.t >= T#2S` срабатывает на цикл раньше, чем при отсчёте с первого активного цикла | время шага отсчитывается с цикла активирующего перехода (`lower/sfc.py`, модель сценариев) — после правки 1232/1232 циклов совпали |
| Последний вызов IEC-действия | ActDrain (N) исполняется ещё раз в цикле после ухода из шага; ActCount (P) — дважды (импульс и последний вызов) | так и в автомате c2s7 |
| CDS_SR / CDS_RS (обратный перевод s7conv) против Standard.SR/RS | 12 шагов, включая SET = RESET = 1 из обоих состояний: совпали оба (`docs/data/compat-controlwin.json`) | КТ-B «CDS_SR/RS сверены в Control Win» |
| Кейс 1, R1: ST′ + coUnit из `s7conv gen-tests` (`tools/codesys/ring_controlwin.py`) | 6 наборов, 39 тестов, 39 прошли, сборка 0/0 (`docs/data/ring-controlwin-r1.json`) | — |
| Трассы R2 корпуса и кольца (`tools/codesys/trace.py`) | корпус: 11 POU, 2227 циклов; кольцо: источник и ST′ по 6 блоков, 50 739 циклов (выходы — на первом и последнем цикле строки сценария, 487 точек) | c2s7.sim повторяет все совпадением (`TEST_REPORT.md`) |
| `s7conv convert --timers` | значения `standard` и `s7compat` (не `native`) | трассы ST′ сняты с `--timers standard` |
