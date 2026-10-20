# Правила C2S7-*

Документ печатается из `src/c2s7/rules/registry.yaml` (тест `tests/unit/test_rules_mapping.py`).
У каждого правила есть корпус `tests/corpus/<id>/{pos,neg}` и `expected.json`; минуты — треугольное
распределение (min, mode, max) на
находку, задано автором по описанию правила, не калибровано. Итог по проекту — Монте-Карло, 10 000 проб,
seed 20261019, находки независимы; P50/P90 в отчёте подписаны «модель, не калибрована».

| Правило | Класс | Что | Минуты (min/mode/max) |
|---|---|---|---|
| [C2S7-ACT](#c2s7-act) | review | ACTION → встраивание | 5/10/30 |
| [C2S7-ADDR-MAP](#c2s7-addr-map) | review | Адрес AT → тег S7 с пересчётом | 2/5/15 |
| [C2S7-ADDR-OVERLAP](#c2s7-addr-overlap) | manual | Наложение %M разной ширины | 20/40/120 |
| [C2S7-ADDR-WORDBIT](#c2s7-addr-wordbit) | manual | Битовый адрес при словной адресации | 5/10/30 |
| [C2S7-GFX-CFCFB](#c2s7-gfx-cfcfb) | review | Обратная связь CFC | 5/10/30 |
| [C2S7-GFX-DOUBLECOIL](#c2s7-gfx-doublecoil) | verify | Двойная катушка | 5/15/45 |
| [C2S7-GFX-EDGE](#c2s7-gfx-edge) | review | Контакт P/N → бит памяти в статике | 2/5/15 |
| [C2S7-GFX-ENO](#c2s7-gfx-eno) | review | ENO идёт дальше по цепи | 10/20/60 |
| [C2S7-GFX-GOTO](#c2s7-gfx-goto) | verify | Неприводимый переход | 15/30/90 |
| [C2S7-GFX-ORDER](#c2s7-gfx-order) | verify | Порядок побочных эффектов в сети | 5/10/30 |
| [C2S7-GFX-SCL](#c2s7-gfx-scl) | review | Сеть вне подмножества FlgNet → SCL | 2/5/15 |
| [C2S7-GFX-SFC](#c2s7-gfx-sfc) | review | SFC → автомат SCL | 10/20/60 |
| [C2S7-GFX-SFCQ](#c2s7-gfx-sfcq) | manual | Квалификатор SFC вне P0 | 15/30/90 |
| [C2S7-IL](#c2s7-il) | review | IL → SCL через ST | 5/10/30 |
| [C2S7-IO-NOMAP](#c2s7-io-nomap) | manual | Нет карты ввода-вывода (--io-map) | 30/60/240 |
| [C2S7-LIB](#c2s7-lib) | manual | Библиотека без аналога в S7 | 30/90/480 |
| [C2S7-NAME-KEYWORD](#c2s7-name-keyword) | review | Имя — ключевое слово SCL | 2/5/15 |
| [C2S7-NAME-LEN](#c2s7-name-len) | manual | Имя длиннее 128 символов | 2/5/15 |
| [C2S7-OOP](#c2s7-oop) | manual | METHOD, PROPERTY, EXTENDS, INTERFACE | 60/120/480 |
| [C2S7-POU-FBINFC](#c2s7-pou-fbinfc) | manual | Экземпляр ФБ внутри FUNCTION | 15/30/90 |
| [C2S7-POU-INCONST](#c2s7-pou-inconst) | review | VAR_INPUT CONSTANT | 1/3/10 |
| [C2S7-POU-INIT](#c2s7-pou-init) | review | Начальные значения Temp и выходов FC → присваивания | 1/3/10 |
| [C2S7-POU-PRG](#c2s7-pou-prg) | review | PROGRAM → FB + экземплярный DB, вызов из OB | 2/5/15 |
| [C2S7-POU-STAT](#c2s7-pou-stat) | review | VAR_STAT в FUNCTION/METHOD → глобальный DB | 5/15/40 |
| [C2S7-PROF-LANG](#c2s7-prof-lang) | impossible | Язык недоступен на CPU | 10/20/60 |
| [C2S7-PROF-REF](#c2s7-prof-ref) | impossible | REF_TO на S7-1200 | 30/60/180 |
| [C2S7-RET](#c2s7-ret) | review | PERSISTENT → Retain | 10/20/60 |
| [C2S7-RING-CHECK](#c2s7-ring-check) | info | Пометка s7conv MIGRATION-CHECK | 0/0/0 |
| [C2S7-RING-LOSS](#c2s7-ring-loss) | manual | Потеря в s7-to-codesys | 10/20/60 |
| [C2S7-RING-TODO](#c2s7-ring-todo) | manual | Пометка s7conv MIGRATION-TODO | 5/15/60 |
| [C2S7-SEM-CTR](#c2s7-sem-ctr) | review | Счётчик: тип CV/PV | 5/10/30 |
| [C2S7-SEM-DIV0](#c2s7-sem-div0) | verify | Целочисленное деление на переменную | 5/10/30 |
| [C2S7-SEM-LIMIT](#c2s7-sem-limit) | verify | LIMIT при MN > MX | 5/10/30 |
| [C2S7-SEM-MUX](#c2s7-sem-mux) | verify | MUX вне диапазона | 5/10/30 |
| [C2S7-SEM-OVERFLOW](#c2s7-sem-overflow) | verify | Разрядность промежуточного результата | 5/15/45 |
| [C2S7-SEM-ROUND](#c2s7-sem-round) | verify | REAL → целое: округление половины | 5/10/30 |
| [C2S7-SEM-SRRS](#c2s7-sem-srrs) | review | SR/RS — крест-накрест | 2/5/15 |
| [C2S7-SEM-TEMP](#c2s7-sem-temp) | review | VAR_TEMP читается до записи | 2/5/15 |
| [C2S7-SEM-TIMER-Q](#c2s7-sem-timer-q) | review | Чтение Q/ET таймера вне вызова | 10/20/60 |
| [C2S7-STD](#c2s7-std) | review | Стандартная функция с другими параметрами | 1/3/10 |
| [C2S7-STD-UTIL](#c2s7-std-util) | manual | Блок библиотеки Util / CAA | 20/45/120 |
| [C2S7-TASK-EVENT](#c2s7-task-event) | manual | Событийная задача | 20/45/120 |
| [C2S7-TASK-LIMIT](#c2s7-task-limit) | manual | Больше циклических задач, чем циклических прерываний CPU | 30/60/120 |
| [C2S7-TASK-OB](#c2s7-task-ob) | review | Задача → OB | 5/10/20 |
| [C2S7-TASK-PRIO-MERGE](#c2s7-task-prio-merge) | review | Разные приоритеты задач слились | 5/15/30 |
| [C2S7-TYPE-64](#c2s7-type-64) | impossible | 64-битный тип на S7-1200 | 15/30/90 |
| [C2S7-TYPE-ALIAS](#c2s7-type-alias) | review | Псевдоним типа | 2/5/15 |
| [C2S7-TYPE-CYR](#c2s7-type-cyr) | verify | Кириллица в String | 5/15/45 |
| [C2S7-TYPE-DATE](#c2s7-type-date) | manual | Арифметика DATE/DT через DWORD | 20/45/120 |
| [C2S7-TYPE-ENUM](#c2s7-type-enum) | review | Перечисление → базовый тип и константы | 5/15/40 |
| [C2S7-TYPE-PTR](#c2s7-type-ptr) | manual | POINTER, ADR, __NEW, REFERENCE TO | 30/90/240 |
| [C2S7-TYPE-RANGE](#c2s7-type-range) | review | Тип-диапазон INT(a..b) | 5/10/30 |
| [C2S7-TYPE-STRLAYOUT](#c2s7-type-strlayout) | manual | Раскладка STRING в памяти | 20/45/120 |
| [C2S7-TYPE-STRLEN](#c2s7-type-strlen) | manual | STRING(n) при n > 254 | 15/30/90 |
| [C2S7-TYPE-TIME](#c2s7-type-time) | review | TIME CODESYS беззнаковый, Time S7 — со знаком | 10/20/60 |
| [C2S7-TYPE-UNION](#c2s7-type-union) | manual | UNION | 30/60/180 |
| [C2S7-TYPE-WSTRING](#c2s7-type-wstring) | review | WSTRING без длины | 1/3/10 |

## C2S7-ACT

**ACTION → встраивание** — класс `review`.

Действий в S7 нет: тело действия встраивается в место вызова (вызов только из своего POU).

Что сделать: Проверить, что действие не вызывается извне.

Источник: ТЗ M5

## C2S7-ADDR-MAP

**Адрес AT → тег S7 с пересчётом** — класс `review`.

Номер в %IW/%ID CODESYS — номер слова/двойного слова, в S7 — номер байта: %IWn → %IW(2n), %IDn → %ID(4n); биты совпадают при байтовой адресации. Адреса каналов в аппаратной конфигурации S7 почти всегда другие.

Что сделать: Сверить адреса с аппаратной конфигурацией TIA.

Источник: проба M0 (docs/PROBES.md §2); s7-to-codesys docs/MAPPING.md «Адресная модель»

## C2S7-ADDR-OVERLAP

**Наложение %M разной ширины** — класс `manual`.

В CODESYS %MX10.0 — бит 0 байта 10, а слово %MW5 — байты 10–11 (little-endian); в S7 %MW10 — байты 10–11 big-endian, бит %M10.0 — бит 8 слова. Совместный доступ разной ширины меняет смысл.

Что сделать: Перенести данные в DB (Guideline V1.4 разд. 3.4) или переставить байты (SWAP).

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operands_addresses.html; s7-to-codesys docs/MAPPING.md «Адресная модель»

## C2S7-ADDR-WORDBIT

**Битовый адрес при словной адресации** — класс `manual`.

На устройстве со словной адресацией битов %IX5.3 — бит 3 слова 5; прямого перевода в байтовый адрес S7 нет.

Что сделать: Назначить канал в аппаратной конфигурации TIA и таблице тегов.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_operands_addresses.html

## C2S7-GFX-CFCFB

**Обратная связь CFC** — класс `review`.

Вход блока CFC берёт выход блока с большим порядком выполнения — значение прошлого цикла; c2s7 хранит его в статике.

Что сделать: Ничего; проверить начальное значение статики.

Источник: справка CODESYS CFC (порядок выполнения); ТЗ M5

## C2S7-GFX-DOUBLECOIL

**Двойная катушка** — класс `verify`.

Одна переменная пишется катушками в нескольких сетях — побеждает последняя по порядку выполнения; порядок сетей TIA сохраняет, но такие места стоит проверить.

Что сделать: Свести запись к одной катушке.

Источник: ТЗ M5

## C2S7-GFX-EDGE

**Контакт P/N → бит памяти в статике** — класс `review`.

У Siemens фронтовый контакт хранит предыдущее значение в явном бите (M или Static); CODESYS прячет память фронта.

Что сделать: Ничего.

Источник: XSD LADFBD_v5 (PContact/NContact, операнд памяти); E§5.2

## C2S7-GFX-ENO

**ENO идёт дальше по цепи** — класс `review`.

CODESYS: ENO = EN; S7: ENO = EN AND NOT ошибка бокса (LAD-справочник 05/2010, прил. C.1). Цепочки ENO, ловящие переполнение, меняют смысл.

Что сделать: Проверить логику, зависящую от ENO.

Источник: https://cache.industry.siemens.com/dl/files/822/45523822/att_82001/v1/s7kop__b.pdf

## C2S7-GFX-GOTO

**Неприводимый переход** — класс `verify`.

Переход не сводится к IF/REPEAT; остаётся GOTO. s7conv такой POU разбирает, но не переносит (stmt.goto — TODO), поэтому он исключён из кольца поведения.

Что сделать: Переписать структурно.

Источник: ТЗ M3; s7-to-codesys docs/MAPPING.md (GOTO — TODO)

## C2S7-GFX-ORDER

**Порядок побочных эффектов в сети** — класс `verify`.

В сети несколько выходов/вызовов; порядок их выполнения в TIA (сверху вниз, слева направо) может отличаться от CODESYS.

Что сделать: Разделить на сети по одному выходу.

Источник: E§5.2 (порядок вычисления)

## C2S7-GFX-SCL

**Сеть вне подмножества FlgNet → SCL** — класс `review`.

Элемент сети не входит в закрытое подмножество LAD/FBD P0; POU переводится в SCL.

Что сделать: Ничего.

Источник: ТЗ M5

## C2S7-GFX-SFC

**SFC → автомат SCL** — класс `review`.

SFC переводится в автомат SCL (шаги — Bool в статике, время шага — TON_TIME, IEC-действия — по порядку справки CODESYS). GRAPH — P1.

Что сделать: Проверить на ПЛК (сценарии в EQUIVALENCE.md).

Источник: https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html

## C2S7-GFX-SFCQ

**Квалификатор SFC вне P0** — класс `manual`.

L/D/SD/DS/SL и флаги SFC в P0 не переводятся.

Что сделать: Разложить на таймеры вручную.

Источник: https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_action_qualifier.html

## C2S7-IL

**IL → SCL через ST** — класс `review`.

IL переводится в ST AST (текущий результат переживает ST) и печатается в SCL; IL → STL — NICE.

Что сделать: Ничего.

Источник: ТЗ M2; IL исключён из МЭК 61131-3 ed. 4

## C2S7-IO-NOMAP

**Нет карты ввода-вывода (--io-map)** — класс `manual`.

У проектов ОВЕН каналы привязаны в дереве устройств, а не через AT; конфигурации устройств в PLCopen нет. Без «Export mappings to CSV» c2s7 не знает, какие переменные связаны с каналами.

Что сделать: Экспортировать карту ввода-вывода устройства в CSV и повторить с --io-map, либо назначить каналы вручную.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_cmd_export_io_mapping_csv.html

## C2S7-LIB

**Библиотека без аналога в S7** — класс `manual`.

SysLibs, CAA, библиотеки ОВЕН, OSCAT, Modbus, Symbol Configuration не имеют прямой замены; c2s7 оставляет заготовку.

Что сделать: Заменить на инструкции S7 (MB_SERVER, TSEND_C, FileReadC ...) или переписать.

Источник: codesys-to-s7.md R§4.8

## C2S7-NAME-KEYWORD

**Имя — ключевое слово SCL** — класс `review`.

Идентификатор совпадает с ключевым словом SCL; c2s7 пишет его в кавычках #"имя" (s7conv такую форму разбирает; TIA — сверить).

Что сделать: Переименовать.

Источник: s7-to-codesys s7conv/lexer.py (кавычки в именах)

## C2S7-NAME-LEN

**Имя длиннее 128 символов** — класс `manual`.

Имена блоков и тегов S7 — до 128 символов (сверить).

Что сделать: Сократить имя.

Источник: codesys-to-s7.md R§4

## C2S7-OOP

**METHOD, PROPERTY, EXTENDS, INTERFACE** — класс `manual`.

Классического ООП в STEP 7 нет (есть в SIMATIC AX). P0 — план уплощения: статика FB в UDT, METHOD → FC с IN_OUT self, PROPERTY → поле или FC Get/Set, EXTENDS → слияние.

Что сделать: Уплощить по плану из MANUAL_STEPS.md.

Источник: codesys-to-s7.md R§2.6, R§4.1

## C2S7-POU-FBINFC

**Экземпляр ФБ внутри FUNCTION** — класс `manual`.

Во FUNCTION CODESYS экземпляр ФБ временный (создаётся на каждый вызов); в FC S7 мультиэкземпляра нет.

Что сделать: Сделать из функции FB или передавать экземпляр через IN_OUT.

Источник: codesys-to-s7.md R§4.1

## C2S7-POU-INCONST

**VAR_INPUT CONSTANT** — класс `review`.

Константный вход CODESYS (только литералы при вызове) переводится в обычный Input.

Что сделать: Ничего.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_var_input_constant.html

## C2S7-POU-INIT

**Начальные значения Temp и выходов FC → присваивания** — класс `review`.

CODESYS инициализирует временные переменные и выходы FUNCTION при каждом вызове (проба M0: выход := 7 на втором вызове); у Temp и выходов FC в S7 начальных значений нет. c2s7 пишет присваивания в начало тела.

Что сделать: Ничего.

Источник: проба M0 (docs/PROBES.md §2)

## C2S7-POU-PRG

**PROGRAM → FB + экземплярный DB, вызов из OB** — класс `review`.

У OB нет статических переменных (секции только Input/Temp/Constant), поэтому программа становится FB "PRG_X" с DB "PRG_X_DB", а её вызов — строкой в теле OB.

Что сделать: Создать OB по TASKS.md и вставить тело из tia/ob/.

Источник: codesys-to-s7.md R§4.1; tia-portal-xml-generator (MIT), elements/interface.py — секции OB [M]

## C2S7-POU-STAT

**VAR_STAT в FUNCTION/METHOD → глобальный DB** — класс `review`.

Статические переменные функции CODESYS живут между вызовами; в FC S7 статики нет — c2s7 выносит их в DB "<POU>_Stat".

Что сделать: Проверить, что функция вызывается из одного места (иначе общая статика).

Источник: ТЗ M5; codesys-to-s7.md R§3 (VAR_STAT в экспортах TIA не встречается)

## C2S7-PROF-LANG

**Язык недоступен на CPU** — класс `impossible`.

STL, GRAPH, CFC на S7-1200 нет (сравнительный список 05/2021).

Что сделать: SCL или S7-1500.

Источник: https://cache.industry.siemens.com/dl/files/648/109797648/att_1067421/v1/s71500_compare_table_en.pdf

## C2S7-PROF-REF

**REF_TO на S7-1200** — класс `impossible`.

REF_TO/REF() есть в STEP 7 для S7-1500 (сравнительный список 05/2021); для S7-1200 FW 4.x не подтверждено.

Что сделать: Переписать без ссылок.

Источник: https://cache.industry.siemens.com/dl/files/648/109797648/att_1067421/v1/s71500_compare_table_en.pdf

## C2S7-RET

**PERSISTENT → Retain** — класс `review`.

PERSISTENT CODESYS переживает загрузку; Retain S7 — нет (после загрузки с переинициализацией значения теряются, нужен резерв памяти или рецептный DB). RETAIN во FUNCTION невозможен.

Что сделать: Резерв памяти для загрузки без переинициализации или рецептный DB.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_preserve_data_with_persistent_variables.html; Guideline V1.4 разд. 3.2.7

## C2S7-RING-CHECK

**Пометка s7conv MIGRATION-CHECK** — класс `info`.

Входная пометка s7conv распознана; повторно не ставится (00-INDEX §4.1).

Что сделать: Ничего.

Источник: 00-INDEX.md §4.1

## C2S7-RING-LOSS

**Потеря в s7-to-codesys** — класс `manual`.

s7conv не перенёс часть конструкции (аргумент, объявление); восстановить её по ST нельзя.

Что сделать: Восстановить по исходному проекту S7.

Источник: s7-to-codesys docs/MAPPING.md

## C2S7-RING-TODO

**Пометка s7conv MIGRATION-TODO** — класс `manual`.

Конструкция пришла из s7-to-codesys непереведённой; c2s7 восстанавливает исходный текст SCL из комментария пометки и оставляет ручной шаг.

Что сделать: Проверить восстановленный текст.

Источник: s7-to-codesys docs/MAPPING.md «Не поддерживается»

## C2S7-SEM-CTR

**Счётчик: тип CV/PV** — класс `review`.

У CTU/CTD/CTUD Standard PV и CV — WORD (насыщение 65535/0, проба M0); c2s7 ставит CTU_UINT. Знаковый приёмник CV → CTx_INT (беззнаковый CTD стоит на нуле, знаковый уходит в минус).

Что сделать: Проверить диапазон счёта.

Источник: проба M0; S7-1200 System Manual §7.3

## C2S7-SEM-DIV0

**Целочисленное деление на переменную** — класс `verify`.

Деление на 0 в CODESYS — исключение и останов задачи (без CheckDiv*), в S7 CPU продолжает работу (результат и ENO — сверить).

Что сделать: Проверять делитель явно.

Источник: s7-to-codesys docs/MAPPING.md (expr.div_int); справка CODESYS POU для неявных проверок

## C2S7-SEM-LIMIT

**LIMIT при MN > MX** — класс `verify`.

CODESYS возвращает MX (проба M0); S7 по сведениям s7-to-codesys возвращает IN и ENO = FALSE — сверить.

Что сделать: Гарантировать MN <= MX или проверить на ПЛК.

Источник: проба M0; s7-to-codesys docs/MAPPING.md, стр. 127

## C2S7-SEM-MUX

**MUX вне диапазона** — класс `verify`.

MUX(K, IN0…INn) при K вне 0…n в CODESYS и S7 ведёт себя по-разному (S7: вход ELSE, ENO) — сверить.

Что сделать: Ограничить K.

Источник: s7-to-codesys docs/MAPPING.md (MUX)

## C2S7-SEM-OVERFLOW

**Разрядность промежуточного результата** — класс `verify`.

CODESYS считает промежуточные результаты целой арифметики не меньше чем в 32 битах (проба M0: DINT := INT(300) * INT(300) = 90000), S7 — в типе операндов (Int переполняется).

Что сделать: Привести операнды к типу результата явно (INT_TO_DINT).

Источник: проба M0 (docs/PROBES.md §2); s7-to-codesys docs/MAPPING.md «Расхождения, которые конвертер не помечает»

## C2S7-SEM-ROUND

**REAL → целое: округление половины** — класс `verify`.

CODESYS округляет половину от нуля (проба M0: REAL_TO_INT(2.5) = 3, (-2.5) = -3). Правило S7 для половины по документации противоречиво — пробник.

Что сделать: Прогнать probe/ на ПЛК; при расхождении — ROUND/TRUNC явно.

Источник: проба M0 (docs/PROBES.md §2); codesys-to-s7.md §7.1 (противоречиво)

## C2S7-SEM-SRRS

**SR/RS — крест-накрест** — класс `review`.

CODESYS SR(SET1, RESET) — установка доминирует = S7 RS; CODESYS RS(SET, RESET1) — сброс доминирует = S7 SR (проба M0, LAD-справочник 05/2010 §1.10–1.11). В SCL инструкций SR/RS нет — c2s7 ставит CDS_SR/CDS_RS.

Что сделать: Ничего; CDS_SR/CDS_RS — в tia/compat/.

Источник: https://cache.industry.siemens.com/dl/files/822/45523822/att_82001/v1/s7kop__b.pdf; проба M0

## C2S7-SEM-TEMP

**VAR_TEMP читается до записи** — класс `review`.

Temp CODESYS инициализируется при каждом вызове, Temp оптимизированного блока S7 — тоже, но значения по умолчанию типа; неоптимизированного — не определены.

Что сделать: Записывать Temp до чтения.

Источник: Programming Guideline V1.4, разд. 2.4

## C2S7-SEM-TIMER-Q

**Чтение Q/ET таймера вне вызова** — класс `review`.

S7-1200 обновляет Q/ET IEC-таймера и при прямом чтении членов (S7-1200 System Manual 04/2012 §7.2, с. 186–187). Идиомы t(IN := NOT t.Q) и чтение t.Q до вызова ведут себя иначе; c2s7 переписывает их на выход вызова Q => #tQ.

Что сделать: Проверить на ПЛК (probe/).

Источник: https://cache.industry.siemens.com/dl/files/465/36932465/att_106119/v1/s71200_system_manual_en-US_en-US.pdf

## C2S7-STD

**Стандартная функция с другими параметрами** — класс `review`.

Строковые функции S7 называют параметры IN/IN1/IN2/L/P, счётчики — R/LD; c2s7 переименовывает параметры и приводит вызов к формальному.

Что сделать: Ничего.

Источник: реестр инструкций s7-lint-vscode (Apache-2.0), SCL-string-functions.yaml; codesys-to-s7.md R§4.3

## C2S7-STD-UTIL

**Блок библиотеки Util / CAA** — класс `manual`.

BLINK, HYSTERESIS, RAMP_*, PID и блоки CAA в P0 не переводятся (CodesysCompat P1); аналоги — LGF и технологические объекты.

Что сделать: Заменить на LGF_* / PID_Compact или написать блок.

Источник: codesys-to-s7.md R§4.8

## C2S7-TASK-EVENT

**Событийная задача** — класс `manual`.

Задачи по событию/статусу CODESYS прямого аналога не имеют (Hardware interrupt OB40+ только для аппаратуры).

Что сделать: Опрос фронта в циклическом OB или прерывание аппаратуры.

Источник: codesys-to-s7.md R§4.5

## C2S7-TASK-LIMIT

**Больше циклических задач, чем циклических прерываний CPU** — класс `manual`.

У S7-1200 — 4 циклических прерывания (R§4.5 [M]); лишние задачи не получают OB.

Что сделать: Объединить задачи или выбрать S7-1500.

Источник: Programming Guideline V1.4, табл. 2-8

## C2S7-TASK-OB

**Задача → OB** — класс `review`.

Тип, период и номер OB внешний исходник не задаёт, а OB1 в исходнике конфликтует с автоматическим [L]; c2s7 пишет только тело OB и TASKS.md, OB создаёт инженер.

Что сделать: Создать OB по TASKS.md (тип, номер, период, приоритет) и вставить тело.

Источник: codesys-to-s7.md R§2.1; s7-to-codesys docs/ASSUMPTIONS.md S6

## C2S7-TASK-PRIO-MERGE

**Разные приоритеты задач слились** — класс `review`.

Приоритетов циклических задач больше, чем уровней до P_max; разные приоритеты CODESYS получили один приоритет OB.

Что сделать: Проверить порядок вытеснения.

Источник: ТЗ M5 (формула приоритетов); S7-1500 Cycle and response times 02/2014

## C2S7-TYPE-64

**64-битный тип на S7-1200** — класс `impossible`.

LInt, ULInt, LWord, LTime на S7-1200 FW 4.x не поддерживаются (сравнительный список 05/2021, сверить).

Что сделать: Выбрать S7-1500 или перейти на 32-битный тип с контролем переполнения.

Источник: https://cache.industry.siemens.com/dl/files/648/109797648/att_1067421/v1/s71500_compare_table_en.pdf

## C2S7-TYPE-ALIAS

**Псевдоним типа** — класс `review`.

PLC data type в S7 — только структура; псевдоним TYPE T : INT заменяется базовым типом.

Что сделать: Ничего, если имя типа не используется во внешних интерфейсах (HMI, связь).

Источник: XSD SW.InterfaceSections_v5 (тип PLC — Struct); ТЗ M5

## C2S7-TYPE-CYR

**Кириллица в String** — класс `verify`.

String S7 — однобайтовый, кодовая страница в TIA задаётся проектом; CODESYS хранит байты как есть. Совпадение текста не подтверждено.

Что сделать: WString для текстов на кириллице или проверка на ПЛК (probe/).

Источник: codesys-to-s7.md R§4.4 [M]

## C2S7-TYPE-DATE

**Арифметика DATE/DT через DWORD** — класс `manual`.

В CODESYS DATE/DT — секунды с 1970 в DWORD, в S7 Date — дни с 1990 (UInt), DT — 8 байт BCD (на S7-1200 — DTL). Преобразования *_TO_DWORD дают разные числа.

Что сделать: Переписать на T_DIFF/T_ADD (S7) или DTL.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_date_and_time.html; codesys-to-s7.md R§4.4

## C2S7-TYPE-ENUM

**Перечисление → базовый тип и константы** — класс `review`.

ENUM CODESYS переводится в базовый тип (INT по умолчанию) и пользовательские константы «<Тип>_<Значение>»; именованные типы значений (NVT, V19+) — NICE.

Что сделать: Импортировать константы из PLCTags.xlsx (лист «User constants»).

Источник: TIA Portal V21 Technical Slides, с. 117 (NVT); ТЗ M5

## C2S7-TYPE-PTR

**POINTER, ADR, __NEW, REFERENCE TO** — класс `manual`.

Указатели S7 (Pointer/Any) — только в неоптимизированных блоках; REFERENCE TO → REF_TO (S7-1500, не в статике FB); динамической памяти нет.

Что сделать: Переписать на ARRAY с индексом, VARIANT или REF_TO (1500).

Источник: Programming Guideline V1.4, разд. 2.8.5; сравнительный список 05/2021

## C2S7-TYPE-RANGE

**Тип-диапазон INT(a..b)** — класс `review`.

В S7 нет типов-диапазонов: подставляется базовый тип, контроль границ CODESYS теряется (с --range-check — LIMIT при присваивании).

Что сделать: Проверить, что значения не выходят за диапазон, или включить --range-check.

Источник: codesys-to-s7.md R§4.4; ТЗ M5

## C2S7-TYPE-STRLAYOUT

**Раскладка STRING в памяти** — класс `manual`.

STRING CODESYS занимает n+1 байт (нуль-терминатор), String S7 — n+2 (длина максимальная и текущая). Наложения (UNION, AT, MemCopy) ломаются.

Что сделать: Убрать наложение строк, копировать посимвольно или через Strg_TO_Chars.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_string.html; S7-1200 System Manual §4.2

## C2S7-TYPE-STRLEN

**STRING(n) при n > 254** — класс `manual`.

String S7 — не больше 254 символов.

Что сделать: WString[n] (до 16382) или массив Char.

Источник: Programming Guideline V1.4, табл. 2-13

## C2S7-TYPE-TIME

**TIME CODESYS беззнаковый, Time S7 — со знаком** — класс `review`.

TIME CODESYS — 32 бита без знака (0…T#49D17H2M47S295MS), Time S7 — DINT мс (±T#24D20H31M23S647MS). Литерал больше 24D20H на S7-1500 переводится в LTime, на S7-1200 невозможен; разность времени, рассчитанная на беззнаковый перенос, в S7 даёт отрицательное значение.

Что сделать: Проверить расчёт времени; для периодов больше 24 суток — LTime (S7-1500) или счёт в DInt/секундах.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_time.html; S7-1200 System Manual 04/2012, табл. 7-20

## C2S7-TYPE-UNION

**UNION** — класс `manual`.

UNION в SCL S7-1500 нет; наложение — AT в неоптимизированном блоке или Serialize/Deserialize.

Что сделать: Переписать на AT в неоптимизированном блоке или явные сдвиги.

Источник: McpGuides.cs (bulaofen0036-coder, MIT) — [M]; codesys-to-s7.md R§3

## C2S7-TYPE-WSTRING

**WSTRING без длины** — класс `review`.

WSTRING CODESYS без длины — 80 символов, WString S7 без длины — 254; c2s7 пишет WString[80].

Что сделать: Ничего.

Источник: https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_datatype_wstring.html; Guideline V1.4 табл. 2-13
