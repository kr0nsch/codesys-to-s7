# Оракулы поведения

Кто решает, что перенесённый код «ведёт себя так же». Оракулов три, у каждого своя область. Оракулы
не голосуют: расхождение любого из них с ожидаемым значением сценария — находка, а не «совпало».

| Оракул | Где работает | Что исполняет | Статус |
|---|---|---|---|
| `c2s7.sim` | CI (ubuntu, windows), локально | источник CODESYS и ST′ (обратный перевод s7conv) | основной для CI |
| stsim s7-to-codesys | CI, локально, только кейс 1 | ST′ + тесты coUnit из `s7conv gen-tests` | второе мнение |
| CODESYS Control Win 3.5.17.30 | только локально (`pytest -m codesys`) | источник и ST′ в настоящем рантайме | эталон, итоги — `TEST_REPORT.md` |

ST′ — ST CODESYS, который `s7conv convert` (клон s7-to-codesys @ `2285760c`) делает из наших
`tia/sources/*`. Наш ST-парсер его читает, поэтому `c2s7.sim` исполняет и источник, и ST′ одной
моделью.

## c2s7.sim

Интерпретатор нашего ST AST (`src/c2s7/sim/`) с семантикой CODESYS. Поведение, которое у CODESYS и S7
расходится, снято пробой M0 в Control Win (`docs/PROBES.md`) и закреплено тестами
`tests/unit/test_sim.py`.

**Подмножество.**

- Типы: BOOL, BYTE/WORD/DWORD/LWORD, SINT…LINT и беззнаковые, REAL (float32, каждое промежуточное
  значение округляется до float32), LREAL, TIME (32 бита без знака, перенос), LTIME, STRING(n),
  массивы с постоянными границами, STRUCT, ENUM, alias, диапазон, ФБ как члены.
- Целые — с переносом по разрядности приёмника; промежуточный результат `INT * INT` — 32 бита (M0:
  `DINT := INT * INT` = 90000).
- Операторы ST: присваивания, `S=`/`R=`, IF/CASE/FOR/WHILE/REPEAT/EXIT/CONTINUE/RETURN, вызовы ФБ с
  формальными параметрами и `=>`, вызовы функций (выходы и локальные переменные функции
  инициализируются на каждом вызове, M0).
- Встроенные ФБ: TON, TOF, TP (часы — моделируемое время строки сценария), R_TRIG, F_TRIG (первый
  вызов с CLK = FALSE не даёт спада, M0), SR (установка доминирует), RS (сброс доминирует),
  CTU/CTD/CTUD (PV/CV — WORD, CTU стоит на 65535, CTD — на 0).
- Функции: SEL, MUX, LIMIT (при MN > MX результат — MX, M0), MIN, MAX, ABS, SQRT, LN, LOG, EXP,
  тригонометрия, EXPT, MOVE, SHL/SHR/ROL/ROR, LEN/LEFT/RIGHT/MID/CONCAT/FIND/INSERT/DELETE/REPLACE,
  преобразования `X_TO_Y` (REAL_TO_INT — половина от нуля: 2.5 → 3, −2.5 → −3, M0), TRUNC.
- Деление целых на 0 и `MOD 0` — ошибка исполнения (в CODESYS — исключение).

**Вне подмножества** (`SimError` с текстом «вне подмножества»): `ARRAY[*]`, POINTER/REFERENCE,
вызов METHOD, позиционный вызов ФБ, JMP в ST (графика понижается `lower/jumps.py` до исполнения),
неизвестные библиотечные вызовы. Строка сценария с такой конструкцией получает `skip` с причиной;
skip считается отдельно (`rows_skipped`, `scenarios_skipped` в `EQUIVALENCE.json`) и не входит ни в
«совпало», ни в «расхождение». На кейсе 1 skip — 0.

**Режим R1** «строка = вызов»: перед строкой часы ставятся на `t_ms`; у проекта с `GVL_S7Clock`
(слой S7Compat s7-to-codesys) ещё `xSimulation := TRUE` и `tSimNow := t_ms`, как у тестов
`gen-tests`. Сравнение с допуском из CSV (`tolerance`).

## stsim (второе мнение, кейс 1)

`s7conv/tests/stsim.py` клона @ `2285760c` не входит в пакет s7conv, поэтому подключается через
`sys.path`; адаптер — `src/c2s7/verify/stsim_adapter.py`, SHA клона проверяется до запуска.

Порядок: `s7conv gen-tests <сценарии> --out <out>/roundtrip/stsim/tests --corpus <копия
tia/sources с расширением .scl>` → наборы `*_ScenarioTest` исполняются stsim на раскладке ST′
(три цикла, F_TRIG — семантика S7, как показала проба M0 и TEST_REPORT s7-to-codesys).

Ограничения stsim: `REAL_TO_*` считается через `round()` Python (банковское округление), набор
встроенных блоков — TON/TOF/TP, R/F_TRIG, LIMIT/MIN/MAX/ABS/SQRT/X_TO_Y и утверждения coUnit.
Расхождение stsim с Control Win — находка.

Запуск: `c2s7 verify out/ring --roundtrip --oracle stsim`; тест —
`tests/ring/test_ring.py::test_ring_stsim_second_oracle` (6 наборов, 39 тестов, 39 прошли).
На корпусе «Заречная» stsim не используется (его наборы строятся только по сценариям кейса 1).

## CODESYS Control Win (эталон)

Локально, через `tools/codesys/` (копия plc-repo-template @ `da0fc917`) и общую блокировку рантайма
(`FileLock` на `codesys-runtime.lock`; рантайм, запущенный другим проектом, используется как есть и не
останавливается; запущенный своим прогоном — останавливается после него). Тесты — `pytest -m codesys`
(без CODESYS — skip). Итоги — `docs/TEST_REPORT.md`.

- **R1** (кейс 1): ST′ + тесты coUnit из `s7conv gen-tests` в Control Win — `tools/codesys/ring_controlwin.py`.
- **R2** «фиксированный цикл»: стенд `PRG_Trace` в задаче TraceTask 10 мс (`tools/codesys/trace.py`):
  строка сценария держится до t_ms следующей, на каждом цикле — входы, один вызов POU, выходы и
  `TIME()` в массивы; хост читает массивы `read_values` пакетами по 2000. c2s7.sim повторяет все
  циклы по записанным `t_ms`, поэтому сравнение детерминировано. Для долгих сценариев кольца выходы
  пишутся только на первом и последнем цикле каждой строки (входы и время — на каждом цикле).
- CodesysCompat: `tools/codesys/check_compat.py` — CDS_SR/CDS_RS против Standard.SR/RS.

Трассы уточнили модель: время шага SFC отсчитывается с цикла активирующего перехода (`PROBES.md` §4).

## Графика

s7conv читает только SCL. Блоки FlgNet (SimaticML) читает наш `verify/s7xml_reader.py` обратно в
ST AST, и `c2s7.sim` сравнивает поведение. Reader и эмиттер делят типы IR и автора — это проверка
самосогласованности, а не независимое доказательство. Независимые проверки — XSD V19/V21
(`tests/formats`) и, в планах, интерпретатор LAD plc-code и импортёр SimaticML s7-to-codesys.

## Чего оракулы не доказывают

Кольцо S7 → CODESYS → S7 показывает согласованность c2s7 и s7conv, а не компиляцию в TIA Portal:
общие ошибки одного автора могут погаситься. Импорт в TIA не проверен (TIA у автора нет);
процедура для человека с TIA — `docs/HARDWARE_VALIDATION.md`.
