// Назначение: Filter backwash sequence
//             Шаговая программа промывки фильтра
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     2.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Sequencer.scl, строки 40–179, FUNCTION_BLOCK "FB_Sequencer", FAMILY Filters
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_Sequencer.scl
// Блок:      FUNCTION_BLOCK "FB_Sequencer"
// Сценарии:  scenarios/FB_Sequencer.csv (модель scenarios/reference/model_fb_sequencer.py)
// -----------------------------------------------------------------------------
// Назначение
//   Шаговая программа промывки скорого фильтра: опорожнение -> водовоздушная
//   (воздушная) продувка -> промывка водой -> заполнение. Шаги — CASE по номеру
//   шага, время шага — один таймер TON_TIME. Экземпляр DB_Backwash.
//
// Логика (нормативное описание; порядок шагов внутри вызова важен)
//   Шаги: 0 IDLE, 10 DRAIN, 20 AIR SCOUR, 30 BACKWASH, 40 REFILL, 90 FAULT.
//   «Рабочий» шаг — номер в диапазоне 10...40 (то есть 10, 20, 30 или 40; других
//   номеров в этом диапазоне алгоритм не создаёт). stepTime — время с вызова, на котором
//   шаг стал текущим (таймер перезапускается в том же вызове, где сменился шаг).
//   1. Фронты: R_TRIG(start), R_TRIG(reset).
//   2. Если stop = TRUE и шаг рабочий: шаг := 0 (прерывание, без аварии и без счёта).
//      Иначе — переход по текущему шагу (не больше одного перехода за вызов):
//        0:  фронт start AND permissive AND NOT stop        -> 10;
//        10: levelLow                                       -> 20;
//            иначе stepTime >= drainTimeout                 -> faultStep := 10, шаг 90;
//        20: stepTime >= airTime                            -> 30;
//        30: stepTime >= washTime                           -> 40;
//        40: levelHigh                                      -> cycleCount + 1, шаг 0;
//            иначе stepTime >= refillTimeout                -> faultStep := 40, шаг 90;
//        90: фронт reset                                    -> faultStep := 0, шаг 0;
//        другое значение                                    -> 0.
//   3. Выходы по шагу после перехода (в том же вызове):
//        drainValve := шаг 10 или 30; airBlower := шаг 20; washPump := шаг 30;
//        inletValve := шаг 40; busy := шаг рабочий; fault := шаг 90;
//        stepText: 'IDLE', 'DRAIN', 'AIR SCOUR', 'BACKWASH', 'REFILL', 'FAULT'.
//   Начальное состояние экземпляра: шаг 0, все выходы FALSE / 0, stepText пустая
//   строка до первого вызова.
// Что проверяет при конвертации
//   CASE с метками-литералами и ELSE, TON_TIME c ET, повторный вызов таймера в
//   одном цикле (сброс и перезапуск), String[20] на выходе, DInt.
// =============================================================================
FUNCTION_BLOCK FB_Sequencer
VAR_INPUT
    start : BOOL;  // Пуск промывки (по фронту)
    stop : BOOL;  // Прерывание (уровень)
    permissive : BOOL;  // Разрешение: другая промывка не идёт, в РЧВ есть вода
    levelLow : BOOL;  // Фильтр опорожнён
    levelHigh : BOOL;  // Фильтр заполнен
    reset : BOOL;  // Сброс аварии (по фронту)
    drainTimeout : TIME := T#60S;  // Предельное время опорожнения
    airTime : TIME := T#30S;  // Длительность продувки
    washTime : TIME := T#40S;  // Длительность промывки
    refillTimeout : TIME := T#90S;  // Предельное время заполнения
END_VAR
VAR_OUTPUT
    stepNo : INT;  // Номер шага
    drainValve : BOOL;  // Задвижка сброса промывной воды
    airBlower : BOOL;  // Воздуходувка
    washPump : BOOL;  // Промывной насос
    inletValve : BOOL;  // Задвижка подачи исходной воды
    busy : BOOL;  // Промывка идёт
    fault : BOOL;  // Авария промывки
    faultStep : INT;  // Шаг, на котором произошла авария
    cycleCount : DINT;  // Число завершённых промывок
    stepText : STRING(20);  // Название шага для HMI
END_VAR
VAR
    tonStep : FB_S7Ton;  // Время шага (ET)
    edgeStart : R_TRIG;
    edgeReset : R_TRIG;
END_VAR
VAR_TEMP
    stepAtEntry : INT;
    stepRunning : BOOL;
END_VAR
VAR CONSTANT
    STEP_IDLE : INT := 0;
    STEP_DRAIN : INT := 10;
    STEP_AIR_SCOUR : INT := 20;
    STEP_BACKWASH : INT := 30;
    STEP_REFILL : INT := 40;
    STEP_FAULT : INT := 90;
    STEP_TIMER_MAX : TIME := T#1D;  // PT таймера шага: только ET, Q не используется
END_VAR
