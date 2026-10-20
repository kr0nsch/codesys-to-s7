// Назначение: Duty/standby alternation of 3 pumps
//             Чередование насосов II подъёма
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.4 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_PumpAlternation.scl, строки 35–134, FUNCTION_BLOCK "FB_PumpAlternation", FAMILY Pumps
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_PumpAlternation.scl
// Блок:      FUNCTION_BLOCK "FB_PumpAlternation"
// Сценарии:  scenarios/FB_PumpAlternation.csv
//            (модель scenarios/reference/model_fb_pump_alternation.py)
// -----------------------------------------------------------------------------
// Назначение
//   Чередование трёх насосов (рабочий/резервный): равномерная наработка за счёт
//   смены ведущего насоса, подхват резервным при недоступности, нехватка насосов.
//   Экземпляр DB_PumpAlt; requests runN уходят в autoStart экземпляров FB_Motor.
//
// Логика (нормативное описание; порядок шагов внутри вызова важен)
//   Насосы 1...3. Порядок обхода от ведущего lead циклический: lead, lead+1, ...
//   (после 3 идёт 1). Начальное значение lead = 1.
//   1. required := LIMIT(0, demand, 3).
//   2. Событие смены ведущего rotate := фронт alternate (R_TRIG)
//      OR (спад условия required > 0 (F_TRIG) AND rotateOnStop).
//      Спад — переход required от > 0 к 0 между двумя вызовами; на первом вызове
//      экземпляра спада нет, даже если required = 0.
//   3. Если lead вне 1...3: lead := 1. Если rotate: ищется следующий доступный
//      насос после lead по кругу (не больше трёх шагов: lead+1, lead+2, lead);
//      найденный становится lead; если доступных нет — lead не меняется.
//      Пока событий нет, lead не меняется, даже если ведущий недоступен.
//   4. Назначение: обход от lead по кругу, runN := availableN AND (назначено < required);
//      назначено считается по уже включённым в этом обходе. Недоступный ведущий
//      пропускается — его подхватывает следующий доступный.
//   5. leadPump := lead; runningCount := число назначенных; shortage := назначено < required.
// Что проверяет при конвертации
//   Array[1..3] of Bool, FOR, REPEAT ... UNTIL, MOD, F_TRIG с выражением на CLK,
//   LIMIT. Внимание: начальное состояние памяти F_TRIG в S7 и CODESYS сверить —
//   первая строка сценариев проверяет, что на первом вызове спада нет.
// =============================================================================
FUNCTION_BLOCK FB_PumpAlternation
VAR_INPUT
    demand : INT;  // Требуемое число насосов 0...3
    available1 : BOOL;  // Насос 1 готов (авто, нет аварии)
    available2 : BOOL;  // Насос 2 готов
    available3 : BOOL;  // Насос 3 готов
    alternate : BOOL;  // Принудительная смена ведущего (по фронту)
    rotateOnStop : BOOL := TRUE;  // Менять ведущего при каждом останове группы
END_VAR
VAR_OUTPUT
    run1 : BOOL;  // Запрос работы насоса 1
    run2 : BOOL;  // Запрос работы насоса 2
    run3 : BOOL;  // Запрос работы насоса 3
    leadPump : INT;  // Номер ведущего насоса
    runningCount : INT;  // Число назначенных насосов
    shortage : BOOL;  // Доступных насосов меньше, чем требуется
END_VAR
VAR
    lead : INT := 1;  // Ведущий насос
    avail : ARRAY[1..3] OF BOOL;  // Готовность насосов
    runReq : ARRAY[1..3] OF BOOL;  // Назначение насосов
    edgeAlternate : R_TRIG;
    // MIGRATION-CHECK: F_TRIG: в S7 на первом вызове с CLK = FALSE спада нет; у F_TRIG CODESYS Standard 3.5.17.0 —
    //                  тоже (тест StandardFTrigMatchesS7 в Control Win); с другой версией Standard повторить этот
    //                  тест (стр. 65)
    edgeStop : F_TRIG;
END_VAR
VAR_TEMP
    k : INT;
    idx : INT;
    candidate : INT;
    tries : INT;
    required : INT;
    assigned : INT;
    rotate : BOOL;
END_VAR
VAR CONSTANT
    PUMP_COUNT : INT := 3;
END_VAR
