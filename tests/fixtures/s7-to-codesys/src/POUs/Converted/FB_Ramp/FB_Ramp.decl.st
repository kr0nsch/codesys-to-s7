// Назначение: Setpoint ramp generator
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Ramp.scl, строки 26–86, FUNCTION_BLOCK "FB_Ramp", FAMILY Control
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_Ramp.scl
// Блок:   FUNCTION_BLOCK "FB_Ramp"
// -----------------------------------------------------------------------------
// Назначение
//   Задатчик интенсивности: плавное изменение уставки давления при её смене
//   оператором, чтобы регулятор не «бросал» насосы. Вызывается в OB
//   "Cyclic interrupt". Экземпляр DB_RampSP.
//
// Логика (нормативное описание; один вызов = один период cycleTime)
//   1. Первый вызов экземпляра (initDone = FALSE): rampValue := target,
//      initDone := TRUE (без разгона с нуля).
//   2. track = TRUE: rampValue := trackValue (мгновенно, приоритет над hold).
//      Иначе hold = TRUE: rampValue не меняется.
//      Иначе шаг вверх не больше rateUp * dt, вниз не больше rateDown * dt
//      (dt — cycleTime в секундах; rateUp/rateDown — ед./с, отрицательные
//      считаются нулём), без перескока через target.
//   3. atTarget := rampValue = target; rising := в этом вызове был шаг вверх и
//      цель ещё не достигнута; falling — то же вниз.
// Что проверяет при конвертации
//   MIN/MAX с именованными параметрами, TIME_TO_DINT, статический флаг первого
//   вызова, ELSIF-цепочка, сравнение Real на равенство (требует проверки).
// =============================================================================
FUNCTION_BLOCK FB_Ramp
VAR_INPUT
    target : REAL;  // Целевое значение
    rateUp : REAL := 0.1;  // Скорость роста, ед./с
    rateDown : REAL := 0.2;  // Скорость снижения, ед./с
    hold : BOOL;  // Заморозить выход
    track : BOOL;  // Следовать за trackValue
    trackValue : REAL;  // Значение для слежения
    cycleTime : TIME := T#100MS;  // Период вызова
END_VAR
VAR_OUTPUT
    rampValue : REAL;  // Выход задатчика
    atTarget : BOOL;  // Выход равен цели
    rising : BOOL;  // Идёт рост
    falling : BOOL;  // Идёт снижение
END_VAR
VAR
    initDone : BOOL;  // Первый вызов выполнен
END_VAR
VAR_TEMP
    dtSeconds : REAL;
    stepUp : REAL;
    stepDown : REAL;
    moving : BOOL;
END_VAR
