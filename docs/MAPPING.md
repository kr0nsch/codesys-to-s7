# Таблицы соответствия CODESYS 3.5 → S7-1200/1500

Документ печатается из `src/c2s7/mapping/*.yaml` (тест `tests/unit/test_mapping.py` проверяет совпадение).
Классы — опорный словарь семейства: `auto` (без потерь, есть тест), `review` (адаптер или описанное
расхождение), `verify` (поведение S7 не подтверждено, есть проба), `manual` (заготовка и шаг в MANUAL_STEPS.md),
`impossible` (в профиле CPU нет средства). Источники — в docs/SOURCES.md; что проверено, а что нет — в
docs/PROBES.md и docs/HARDWARE_VALIDATION.md. Импорт в TIA Portal автором не проверялся.

## Общее: типы, секции, адреса, объекты

| CODESYS | S7 (TIA Portal) | Класс | Источник | Тест |
|---|---|---|---|---|
| BOOL…LREAL, BYTE…DWORD | те же (Bool, Int, DInt, Real…) | auto | сравнительный список 05/2021 | `tests/unit/test_reverse_rules.py` |
| LINT, ULINT, LWORD, LTIME | те же на S7-1500; на S7-1200 — C2S7-TYPE-64 | auto / impossible | сравнительный список 05/2021 (сверить) | `tests/corpus/C2S7-TYPE-64` |
| BIT; __XWORD, __UXINT, __XINT | Bool; DWord/UDInt/DInt | review | codesys-to-s7.md R§4.4 | `tests/unit/test_types.py` |
| TIME | Time; литерал > T#24D20H31M23S647MS → LTime (1500) или impossible; разность — находка | review | справка CODESYS TIME; S7-1200 Manual табл. 7-20 | `tests/corpus/C2S7-TYPE-TIME` |
| DATE, DT, TOD, LDT | Date, Date_And_Time, Time_Of_Day; арифметика через *_TO_DWORD → C2S7-TYPE-DATE | review / manual | R§4.4 | `tests/corpus/C2S7-TYPE-DATE` |
| STRING / STRING(n ≤ 254) / n > 254 | String[80] / String[n] / manual | auto / manual | справка CODESYS STRING; Guideline V1.4 табл. 2-13 | `tests/corpus/C2S7-TYPE-STRLEN` |
| WSTRING / WSTRING(n) | WString[80] / WString[n] | review | Guideline V1.4 табл. 2-13 | `tests/corpus/C2S7-TYPE-WSTRING` |
| STRUCT | TYPE "X" STRUCT … END_STRUCT (.udt) | auto | экспорты TIA (R§3) | `tests/ring` |
| псевдоним TYPE T : INT | базовый тип | review | XSD InterfaceSections_v5 | `tests/corpus/C2S7-TYPE-ALIAS` |
| диапазон INT(0..100) | базовый тип + C2S7-TYPE-RANGE | review | ТЗ M5 | `tests/corpus/C2S7-TYPE-RANGE` |
| ENUM | базовый тип + пользовательские константы <Тип>_<Значение> | review | слайды V21 с. 117 (NVT — NICE) | `tests/corpus/C2S7-TYPE-ENUM` |
| UNION | manual (AT в неоптимизированном блоке) | manual | McpGuides.cs [M] | `tests/corpus/C2S7-TYPE-UNION` |
| ARRAY / ARRAY[*] | Array[..] of / Array[*] (только InOut) | auto / verify | R§4.2 | `tests/unit/test_reverse_rules.py` |
| POINTER, ADR, __NEW / REFERENCE TO | Variant (заготовка) / REF_TO (1500) | manual / verify | Guideline V1.4 разд. 2.8.5 | `tests/corpus/C2S7-TYPE-PTR` |
| VAR_INPUT/OUTPUT/IN_OUT, VAR, VAR_TEMP, VAR CONSTANT | те же; VAR функции → VAR_TEMP | auto | экспорты TIA | `tests/unit/test_reverse_rules.py` |
| VAR_STAT в FUNCTION | глобальный DB "<POU>_Stat" | review | ТЗ M5 | `tests/corpus/C2S7-POU-STAT` |
| VAR_EXTERNAL | прямое обращение к DB | auto | ТЗ M5 | `tests/unit/test_convert.py` |
| VAR_INPUT CONSTANT | Input + находка | review | справка CODESYS | `tests/corpus/C2S7-POU-INCONST` |
| начальные значения Temp и выходов FC | присваивания в начале тела | review | проба M0 | `tests/corpus/C2S7-POU-INIT` |
| RETAIN / PERSISTENT / RETAIN в FUNCTION | VAR RETAIN / то же + C2S7-RET / manual | auto / review / manual | Guideline V1.4 разд. 3.2.7 | `tests/corpus/C2S7-RET` |
| AT %I/%Q | теги (--io-map); %IXa.b → %Ia.b, %IWn → %IW(2n), %IDn → %ID(4n) | review | проба M0; s7conv MAPPING «Адресная модель» | `tests/corpus/C2S7-ADDR-MAP` |
| пословные биты (--cds-bit-addressing word) | manual | manual | справка CODESYS операнды | `tests/corpus/C2S7-ADDR-WORDBIT` |
| AT %M; наложение %MX/%MB/%MW/%MD | DB "DB_Markers" или --markers keep; разная ширина — keep + C2S7-ADDR-OVERLAP | review / manual | s7conv MAPPING addr.overlap | `tests/corpus/C2S7-ADDR-OVERLAP` |
| без --io-map | C2S7-IO-NOMAP, пустой IO_MAP.csv | manual | справка CODESYS Export mappings to CSV | `tests/corpus/C2S7-IO-NOMAP` |
| GVL / VAR_GLOBAL CONSTANT | глобальный DB (GVL.x → "GVL".x) / пользовательские константы | auto | R§4.1 | `tests/unit/test_reverse_rules.py` |
| ФБ в GVL | одиночный DB "<GVL>_<экземпляр>" (в кольце — имя экземпляра) | review | ТЗ M5 | `tests/unit/test_convert.py` |
| PROGRAM | FB "PRG_X" + DB "PRG_X_DB" + вызов в теле OB | review | R§4.1 | `tests/corpus/C2S7-POU-PRG` |
| FUNCTION_BLOCK / FUNCTION | FB / FC : <тип>, #F := … | auto | экспорты TIA | `tests/unit/test_reverse_rules.py` |
| ФБ внутри FUNCTION | manual | manual | R§4.1 | `tests/corpus/C2S7-POU-FBINFC` |
| ACTION | встраивание в место вызова | review | ТЗ M5 | `tests/corpus/C2S7-ACT` |
| METHOD, PROPERTY, EXTENDS / INTERFACE | P0 — план уплощения (MANUAL_STEPS.md) | manual | R§2.6, R§4.1 | `tests/corpus/C2S7-OOP` |
| задачи циклические | OB30…38, дальше с OB123; приоритет P = P_max − r (формула ТЗ M5) | review | S7-1500 Cycle times 02/2014 | `tests/unit/test_tasks.py` |
| freewheeling / старт / событие | OB1 (program cycle) / OB100 / manual | review / manual | R§4.5 | `tests/unit/test_tasks.py` |
| задач больше, чем OB профиля; слияние приоритетов | C2S7-TASK-LIMIT / C2S7-TASK-PRIO-MERGE | manual / review | Guideline V1.4 табл. 2-8 | `tests/corpus/C2S7-TASK-LIMIT` |

## ST → SCL

| CODESYS | S7 (TIA Portal) | Класс | Источник | Тест |
|---|---|---|---|---|
| обращения, операторы | #x, "DB".x, "тег"; скобки по приоритетам; EXPT → ** | auto | экспорты TIA; s7conv MAPPING | `tests/unit/test_printer.py` |
| ключевое слово SCL как имя | #"x" | review | s7conv lexer.py (TIA — сверить) | `tests/corpus/C2S7-NAME-KEYWORD` |
| IF/CASE/FOR/WHILE/REPEAT, EXIT, CONTINUE, RETURN | те же с ; после END_* | auto | экспорты TIA | `tests/unit/test_reverse_rules.py` |
| позиционные вызовы функций | формальные по реестру инструкций | auto | реестр s7-lint (Apache-2.0) | `tests/unit/test_reverse_rules.py` |
| S= / R= | IF … THEN x := TRUE/FALSE | auto | ТЗ M5 | `tests/unit/test_printer.py` |
| a := b := c | разбиение на два присваивания | auto | ТЗ M5 | `tests/unit/test_parser.py` |
| REF= | REF() (1500) | verify | сравнительный список 05/2021 | `tests/corpus/C2S7-PROF-REF` |
| w.3 | #w.%X3 | auto | s7conv MAPPING | `tests/unit/test_reverse_rules.py` |
| JMP / метки | IF/REPEAT (jumps.py) или GOTO + C2S7-GFX-GOTO | auto / verify | ТЗ M3 | `tests/unit/test_jumps.py` |
| CONCAT/LEFT/MID/INSERT/DELETE/REPLACE/FIND/LEN | параметры IN/IN1/IN2/L/P | review | реестр s7-lint SCL-string-functions.yaml | `tests/corpus/C2S7-STD` |
| REAL_TO_*INT | то же; округление половины — пробник | verify | проба M0 | `tests/corpus/C2S7-SEM-ROUND` |
| целое деление на переменную | то же + C2S7-SEM-DIV0 | verify | s7conv MAPPING expr.div_int | `tests/corpus/C2S7-SEM-DIV0` |
| INT*INT в DINT | то же + C2S7-SEM-OVERFLOW | verify | проба M0 | `tests/corpus/C2S7-SEM-OVERFLOW` |
| MUX; LIMIT при MN > MX | MUX(K, IN0…); LIMIT(MN, IN, MX) — пробник | verify | s7conv MAPPING стр. 127; проба M0 | `tests/corpus/C2S7-SEM-LIMIT` |
| TON/TOF/TP (L-) | TON_TIME… (*_LTIME); t(IN := NOT t.Q) и чтение t.Q до вызова → Q => #t_Q | review | S7-1200 Manual 04/2012 §7.2, с. 186–187 | `tests/corpus/C2S7-SEM-TIMER-Q` |
| CTU/CTD/CTUD | CTU_UINT/CTD_UINT/CTUD_UINT; знаковый приёмник CV → CTx_INT; RESET→R, LOAD→LD | review | проба M0; S7-1200 Manual §7.3 | `tests/corpus/C2S7-SEM-CTR` |
| R_TRIG / F_TRIG | те же (F_TRIG Standard 3.5.17.0 = S7) | auto | s7-to-codesys TEST_REPORT; проба M0 | `tests/unit/test_reverse_rules.py` |
| SR / RS | крест-накрест: CDS_SR/CDS_RS (CodesysCompat) | review | LAD-справочник 05/2010 §1.10–1.11; проба M0 | `tests/corpus/C2S7-SEM-SRRS` |
| EN/ENO | C2S7-GFX-ENO (ENO S7 = EN AND NOT ошибка) | review | LAD-справочник прил. C.1 | `tests/corpus/C2S7-GFX-ENO` |
| Util (BLINK, HYSTERESIS, RAMP_*, PID…) | manual (CodesysCompat P1) | manual | R§4.8 | `tests/corpus/C2S7-STD-UTIL` |
| TIME() | TIME_TCK() (по CPU сверить) | verify | сравнительный список 05/2021 | `tests/unit/test_reverse_rules.py` |
| CAA, SysLibs, OSCAT, библиотеки ОВЕН, SIZEOF | C2S7-LIB | manual / impossible | R§4.8 | `tests/corpus/C2S7-LIB` |

## Графические языки и IL

| CODESYS | S7 (TIA Portal) | Класс | Источник | Тест |
|---|---|---|---|---|
| LD: контакты НО/НЗ, ветви, катушки ( ) (/) (S) (R) | LAD (FlgNet V19/V21): Contact, Coil, SCoil, RCoil, параллельные провода | auto | XSD LADFBD_v5; эталонный набор [M] | `tests/unit/test_flgnet.py` |
| LD: контакт P/N | PContact/NContact с битом памяти в статике | review | XSD LADFBD_v5 | `tests/corpus/C2S7-GFX-EDGE` |
| FBD: AND/OR/XOR/NOT, сравнения, ADD/SUB/MUL/DIV, MOVE/SEL/LIMIT | FBD (FlgNet): A/O/X, Not, Gt…, Add…, Move, Sel, Limit | auto | XSD LADFBD_v5 | `tests/unit/test_flgnet.py` |
| LD/FBD: TON/TOF/TP, CTU, вызов FB/FC | Part TON Version=1.0 + TemplateValue; Call | auto | XSD; эталонный набор [M] | `tests/unit/test_flgnet.py` |
| LD/FBD: Jump/Label/Return | JMP/LABEL/RET | review | XSD LADFBD_v5 | `tests/unit/test_flgnet.py` |
| двойная катушка | та же + C2S7-GFX-DOUBLECOIL | verify | ТЗ M5 | `tests/corpus/C2S7-GFX-DOUBLECOIL` |
| вне подмножества P0 | POU → SCL (C2S7-GFX-SCL) | review | ТЗ M5 | `tests/corpus/C2S7-GFX-SCL` |
| LD/FBD → SCL (всегда) | сеть → операторы по потоку питания/данных | auto | E§5.1 (алгоритм) | `tests/property/test_net_truth.py` |
| CFC | SCL по executionOrderId; обратная связь → статика с прошлым значением | review | справка CODESYS CFC | `tests/corpus/C2S7-GFX-CFCFB` |
| SFC: шаги, переходы, альтернатива, параллель, прыжок | автомат SCL (Bool шагов, TON_TIME времени шага) | review | справка CODESYS SFC (порядок обработки) | `tests/property/test_sfc_automaton.py` |
| SFC: N/S/R/P, действие шага | в автомате по порядку справки CODESYS | review | справка CODESYS SFC qualifiers | `tests/property/test_sfc_automaton.py` |
| SFC: L/D/SD/DS/SL, флаги | manual (P1) | manual | справка CODESYS SFC qualifiers | `tests/corpus/C2S7-GFX-SFCQ` |
| SFC → GRAPH (1500) | P1, экспериментально | manual | XSD Graph_v6 | `—` |
| IL: LD/ST/S/R, логика с N и скобками, арифметика, сравнения, JMP/JMPC/JMPCN, CAL, RET | через ST AST → SCL | review | МЭК 61131-3 ed. 3 (IL) | `tests/unit/test_il.py` |

## Обратные правила к строкам «авто» s7-to-codesys

Каждой строке «авто» таблицы s7-to-codesys `docs/MAPPING.md` @ `2285760c` соответствует обратное правило c2s7;
пример и ожидаемый фрагмент SCL проверяет `tests/unit/test_reverse_rules.py`, всё вместе — кольцо (`tests/ring`).
Строки «проверка»/TODO не зеркалируются. Известный дефект 1.0.0 — одноимённые SR/RS (их стр. 93) — не копируется.

| Стр. | S7 | Выход s7conv | Обратно (c2s7) |
|---|---|---|---|
| 19 | `FUNCTION_BLOCK "FB_X"` | FUNCTION_BLOCK FB_X | `FUNCTION_BLOCK "FB_X"` |
| 20 | `FUNCTION "FC_X" : Real` | FUNCTION FC_X : REAL | `FUNCTION "FC_X" : Real` |
| 21 | `ORGANIZATION_BLOCK "Main"` | PROGRAM PRG_Main + tasks.json sources «Main (OB1)» | `ORGANIZATION_BLOCK "Main"` |
| 22 | `DATA_BLOCK с VAR (глобальный)` | {attribute 'qualified_only'} VAR_GLOBAL | `DATA_BLOCK "GVL_X"` |
| 23 | `экземплярный DATA_BLOCK "DB" "FB"` | GVL_InstanceDBs: DB : FB; | `DATA_BLOCK "DB_P101"` |
| 24 | `DATA_BLOCK "DB" "UDT_X"` | GVL_InstanceDBs: DB : UDT_X; | `DATA_BLOCK "DB_RecipeActive"` |
| 25 | `DATA_BLOCK "T_DB" IEC_TIMER` | GVL_InstanceDBs: T_DB : TON; | `IEC_TIMER` |
| 27 | `TYPE "UDT_X" STRUCT` | TYPE UDT_X : STRUCT a : INT; END_STRUCT END_TYPE | `TYPE "UDT_X"` |
| 28 | `анонимный Struct` | DUT ST_<блок>_<поле> | `Struct` |
| 39 | `VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT` | VAR_INPUT a : BOOL; END_VAR | `VAR_INPUT` |
| 40 | `VAR (статические ФБ)` | VAR a : INT; END_VAR | `   VAR ` |
| 42 | `VAR NON_RETAIN` | VAR a : INT; END_VAR | `a : Int;` |
| 44 | `VAR_TEMP в ФБ и OB` | VAR_TEMP t : INT; END_VAR | `VAR_TEMP` |
| 45 | `VAR_TEMP в FC` | VAR t : INT; END_VAR | `VAR_TEMP` |
| 46 | `VAR CONSTANT` | VAR CONSTANT C : INT := 3; END_VAR | `VAR CONSTANT` |
| 50 | `атрибуты InstructionName, LibVersion` | VAR t : TON; END_VAR | `{InstructionName := 'TON_TIME'; LibVersion := '1.0'}` |
| 55 | `символы вне ASCII, пробелы в именах` | — | — (транслитерация s7conv необратима) |
| 61 | `Bool, Byte, Word, DWord, LWord` | WORD | `Word` |
| 62 | `SInt…ULInt` | UDINT | `UDInt` |
| 63 | `Real, LReal` | LREAL | `LReal` |
| 64 | `Time` | TIME | `Time` |
| 65 | `LTime` | LTIME | `LTime` |
| 67 | `Date` | DATE | `Date` |
| 68 | `Time_Of_Day` | TOD | `Time_Of_Day` |
| 69 | `Date_And_Time` | DT | `Date_And_Time` |
| 71 | `String` | STRING(254) | `String[254]` |
| 72 | `String[n], WString[n]` | STRING(20) | `String[20]` |
| 74 | `Array[a..b] of T` | ARRAY[1..8] OF REAL | `Array[1..8] of Real` |
| 76 | `"UDT_X", "FB_X"` | UDT_DeviceStatus | `"UDT_DeviceStatus"` |
| 86 | `TON_TIME, TOF_TIME, TP_TIME` | TON | `TON_TIME` |
| 89 | `IEC_TIMER` | T_DB : TON (GVL_InstanceDBs) | `IEC_TIMER` |
| 90 | `R_TRIG` | R_TRIG | `R_TRIG` |
| 124 | `NORM_X` | F_NormX(rMin := 0.0, rValue := x, rMax := 1.0) | `NORM_X(MIN := ` |
| 125 | `SCALE_X` | F_ScaleX(rMin := 0.0, rValue := x, rMax := 1.0) | `SCALE_X(MIN := ` |
| 127 | `LIMIT(MN := a, IN := x, MX := b)` | r := LIMIT(0, r, 10); | `LIMIT(MN := 0, IN := #r, MX := 10)` |
| 128 | `MIN, MAX` | r := MAX(r, 1); | `MAX(IN1 := #r, IN2 := 1)` |
| 129 | `SEL, MUX` | r := SEL(b, 1, 2); | `SEL(G := #b, IN0 := 1, IN1 := 2)` |
| 130 | `ABS, SQRT, …, EXPT` | x := EXPT(x, 2.0); | `#x := #x ** 2.0;` |
| 131 | `SQR(x)` | — | — (x * x (s7conv) — обратно не восстанавливается: эквивалентно) |
| 134 | `SHL, SHR, ROL, ROR` | w := SHL(w, 2); | `SHL(IN := #w, N := 2)` |
| 135 | `CONCAT, LEN, LEFT, …` | s := CONCAT(s, 'x'); | `CONCAT(IN1 := #s, IN2 := 'x')` |
| 136 | `X_TO_Y` | x := INT_TO_REAL(i); | `INT_TO_REAL(#i)` |
| 150 | `T#5s, TIME#1h30m` | t := T#1h30m; | `T#1H30M` |
| 152 | `LT#5s` | lt := LTIME#5s; | `LT#5S` |
| 154 | `D#, TOD#, DT#` | d := D#2024-01-31; | `D#2024-01-31` |
| 155 | `16#FF, 2#1010, 8#17` | w := 16#FF; | `16#FF` |
| 156 | `B#16#0F, W#16#FFFF` | w := WORD#16#FFFF; | `WORD#16#FFFF` |
| 157 | `L#100` | d := DINT#100; | `DINT#100` |
| 158 | `INT#-5, REAL#1.5, BOOL#TRUE` | i := INT#-5; | `INT#-5` |
| 159 | `'текст'` | s := 'a$'b'; | `'a$'b'` |
| 160 | `WSTRING#'abc'` | ws := "abc"; | `WSTRING#'abc'` |
| 168 | `#x` | x := 1.0; | `#x := 1.0;` |
| 169 | `&` | b := b AND b; | `#b AND #b` |
| 170 | `a ** b` | x := EXPT(x, 3.0); | `#x ** 3.0` |
| 171 | `MOD, NOT, AND, OR, XOR, сравнения` | b := NOT (i MOD 2 = 0) XOR b; | `NOT (#i MOD 2 = 0) XOR #b` |
| 175 | `x += e` | — | — (x := x + e (s7conv) — обратно как присваивание: эквивалентно) |
| 177 | `#w.%X3` | b := w.3; | `#w.%X3` |
| 181 | `IF/CASE/FOR/WHILE/REPEAT/EXIT/CONTINUE/RETURN` | FOR i := 1 TO 3 DO IF b THEN EXIT; END_IF END_FOR | `END_FOR;` |
| 182 | `REGION` | // REGION X ... // END_REGION X | `REGION ` |
| 184 | `#FC_X := ...` | FC_X := 1; | `#FC_X := 1;` |
| 187 | `комментарии` | x := 1.0; // комментарий | `// комментарий` |
| 188 | `пустые строки` | — | — (не сравниваются (norm.comments)) |
| 197 | `"DB".m` | GVL_X.a := 1; | `"GVL_X".a := 1;` |
| 198 | `"IDB".m, "IDB"(...)` | GVL_InstanceDBs.DB_P101.runCmd | `"DB_P101".runCmd` |
| 199 | `"Тег" с адресом` | GVL_IO.P101_Run | `"P101_Run"` |
| 200 | `"Тег" без адреса` | — | — (GVL_Tags в корпусе нет) |
| 201 | `константа пользователя` | VAR_GLOBAL CONSTANT C_MAX : INT := 5; END_VAR | `User constants` |
| 204 | `%I0.0, %Q4.1, %M12.1` | %IX0.0 | `%I0.0` |
| 205 | `%IB3, %IW64, %QW80, %MD20` | %IW32 | `%IW64` |
| 242 | `VAR RETAIN в глобальном DB` | VAR_GLOBAL RETAIN r : REAL; END_VAR | `VAR RETAIN` |
| 244 | `NON_RETAIN` | VAR_GLOBAL a : INT; END_VAR | `NON_RETAIN` |
| 246 | `экземплярный DB` | GVL_InstanceDBs | `DATA_BLOCK "DB_Mode"` |
| 248 | `BEGIN a := 5;` | VAR_GLOBAL a : INT := 5; END_VAR | `a : Int := 5;` |
| 249 | `BEGIN cfg.high := 16.0;` | cfg : UDT := (high := 16.0) | `pressureCfg.rangeHigh := 16.0;` |
| 250 | `BEGIN arr[1] := 0.5;` | arr : ARRAY[..] OF REAL := [..] | `doseStep` |
| 251 | `BEGIN feedbackTime := T#5S; (экземплярный)` | DB_P101 : FB_Motor := (feedbackTime := T#5S) | `feedbackTime := T#5S;` |
| 252 | `BEGIN типизированного DB` | DB : UDT := (поле := ...) | `name := 'SUMMER';` |
| 265 | `OB1 «Main»` | PRG_Main в MainTask (sources «Main (OB1)») | `ORGANIZATION_BLOCK "Main"` |
| 266 | `OB30…OB38` | PRG_Cyclic_interrupt в Task_OB30 | `ORGANIZATION_BLOCK "Cyclic interrupt"` |
