// Назначение: Flow totalizer
//             Интегратор расхода с отсечкой малых расходов и импульсным выходом
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Totalizer.scl, строки 34–109, FUNCTION_BLOCK "FB_Totalizer", FAMILY Analog
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// MIGRATION-CHECK: VAR RETAIN в ФБ: в CODESYS при RETAIN-переменной в retain-памяти хранится весь экземпляр ФБ, в
//                  S7 — только эти переменные (сверить с источником) (стр. 61)
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_Totalizer.scl
// Блок:      FUNCTION_BLOCK "FB_Totalizer"
// Сценарии:  scenarios/FB_Totalizer.csv (модель scenarios/reference/model_fb_totalizer.py)
// -----------------------------------------------------------------------------
// Назначение
//   Счётчик объёма по мгновенному расходу (интегрирование м3/ч -> м3).
//   Вызывается в циклическом OB с постоянным периодом; период передаётся
//   параметром cycleTime (в OB "Cyclic interrupt" — T#100MS). Экземпляр DB_FQ101.
//   Объём за всё время хранится в сохраняемой статической переменной (VAR RETAIN).
//
// Логика (нормативное описание; один вызов = один период cycleTime)
//   1. cutoffActive := flow < lowFlowCutoff (отрицательный расход тоже ниже отсечки).
//   2. dt := cycleTime в секундах (TIME_TO_DINT(cycleTime) / 1000.0, LReal).
//      dV := flow * dt / 3600.0 (м3, LReal), если enable = TRUE и cutoffActive = FALSE;
//      иначе dV := 0.0.
//   3. lifetimeAcc := lifetimeAcc + dV (RETAIN; reset на него не действует);
//      lifetimeTotal := lifetimeAcc.
//   4. pulse := FALSE.
//      Если reset = TRUE (уровень): total := 0.0, pulseCount := 0, остаток импульса := 0.0;
//      в таком вызове total не интегрируется.
//      Иначе: total := total + dV; остаток := остаток + dV;
//             если pulseVolume > 0 и остаток >= pulseVolume:
//                 pulse := TRUE, pulseCount := pulseCount + 1, остаток := остаток - pulseVolume.
//      Не больше одного импульса за вызов: при dV > pulseVolume импульсы «догоняют»
//      в следующих вызовах.
//   Начальное состояние экземпляра: все выходы 0 / FALSE, остаток 0.0, lifetimeAcc 0.0.
// Что проверяет при конвертации
//   LReal, TIME_TO_DINT, DINT_TO_LREAL, REAL_TO_LREAL, VAR RETAIN в ФБ
//   (-> RETAIN/PERSISTENT в CODESYS), вызов с периодом из циклического OB.
// =============================================================================
FUNCTION_BLOCK FB_Totalizer
VAR_INPUT
    flow : REAL;  // Мгновенный расход, м3/ч
    cycleTime : TIME := T#100MS;  // Период вызова блока
    lowFlowCutoff : REAL := 0.5;  // Отсечка малых расходов, м3/ч
    enable : BOOL := TRUE;  // Интегрирование разрешено
    reset : BOOL;  // Сброс сменного счётчика (уровень)
    pulseVolume : REAL := 1.0;  // Объём на один импульс, м3
END_VAR
VAR_OUTPUT
    total : LREAL;  // Объём с последнего сброса, м3
    lifetimeTotal : LREAL;  // Объём за всё время, м3
    pulseCount : DINT;  // Число импульсов с последнего сброса
    pulse : BOOL;  // Импульс на один вызов при каждом pulseVolume
    cutoffActive : BOOL;  // Расход ниже отсечки
END_VAR
VAR
    pulseAcc : LREAL;  // Остаток объёма до следующего импульса, м3
END_VAR
VAR RETAIN
    lifetimeAcc : LREAL;  // Объём за всё время, м3 (сохраняется при перезапуске)
END_VAR
VAR_TEMP
    dtSeconds : LREAL;
    deltaVolume : LREAL;
END_VAR
VAR CONSTANT
    SECONDS_PER_HOUR : LREAL := 3600.0;
    MS_PER_SECOND : LREAL := 1000.0;
END_VAR
