// Назначение: Analog input scaling with limits
//             Масштабирование канала 0...27648 в инженерные единицы, уставки с гистерезисом
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.3 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_AnalogIn.scl, строки 45–160, FUNCTION_BLOCK "FB_AnalogIn", FAMILY Analog
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_AnalogIn.scl
// Блок:      FUNCTION_BLOCK "FB_AnalogIn"
// Сценарии:  scenarios/FB_AnalogIn.csv (эталонная модель
//            scenarios/reference/model_fb_analog_in.py написана по этому описанию)
// -----------------------------------------------------------------------------
// Назначение
//   Обработка аналогового входа: перевод значения канала S7 (номинал 0...27648)
//   в инженерные единицы через NORM_X/SCALE_X, диагностика канала, четыре уставки
//   с гистерезисом, имитация, слово состояния для HMI.
//   Экземпляры: DB_PT101 (давление в коллекторе 0...16 бар), DB_LT101 (уровень
//   РЧВ), DB_FT101 (расход).
//
// Логика (нормативное описание; один вызов ФБ — один шаг)
//   1. Диагностика по сырому значению raw (границы — представление аналоговых
//      величин S7 для диапазонов 0...20 / 4...20 мА; сверить с руководством на модуль):
//        channelFault := raw > 32511 OR raw < -4864
//                        (вне зон перегрузки: 32767 — переполнение/обрыв,
//                        -32768 — антипереполнение);
//        overrange    := NOT channelFault AND raw > 27648;
//        underrange   := NOT channelFault AND raw < 0.
//   2. Значение value и достоверность valid:
//        simulation = TRUE      -> value := simValue, valid := TRUE
//                                  (флаги п. 1 считаются, но на value не влияют);
//        иначе channelFault     -> value := substitute, valid := FALSE;
//        иначе                  -> rawClamped := LIMIT(0, raw, 27648);
//                                  value := SCALE_X(rangeLow, NORM_X(0, rawClamped, 27648), rangeHigh),
//                                  т. е. value = rangeLow + (rangeHigh - rangeLow) * rawClamped / 27648;
//                                  valid := TRUE.
//   3. Уставки с гистерезисом hysteresis. Если valid = FALSE, все четыре флага := FALSE.
//      Иначе каждый флаг меняется независимо, между порогами сохраняет значение:
//        alarmHH: TRUE при value >= limitHH; FALSE при value < limitHH - hysteresis;
//        warnH:   TRUE при value >= limitH;  FALSE при value < limitH - hysteresis;
//        warnL:   TRUE при value <= limitL;  FALSE при value > limitL + hysteresis;
//        alarmLL: TRUE при value <= limitLL; FALSE при value > limitLL + hysteresis.
//   4. statusWord: бит 0 — valid, 1 — channelFault, 2 — overrange, 3 — underrange,
//      4 — alarmHH, 5 — warnH, 6 — warnL, 7 — alarmLL, 8 — simulation; биты 9...15 = 0.
//   Начальное состояние экземпляра: все выходы FALSE / 0.
// Что проверяет при конвертации
//   NORM_X/SCALE_X -> F_NormX/F_ScaleX; LIMIT с именованными параметрами MN/IN/MX;
//   локальные константы #CONST; REGION; запись битов Word через .%Xn.
// =============================================================================
FUNCTION_BLOCK FB_AnalogIn
VAR_INPUT
    raw : INT;  // Значение канала модуля AI
    rangeLow : REAL := 0.0;  // Инж. значение при raw = 0
    rangeHigh : REAL := 16.0;  // Инж. значение при raw = 27648
    limitHH : REAL := 14.0;  // Уставка аварийно высокого значения
    limitH : REAL := 12.0;  // Уставка предупредительно высокого значения
    limitL : REAL := 2.0;  // Уставка предупредительно низкого значения
    limitLL : REAL := 1.0;  // Уставка аварийно низкого значения
    hysteresis : REAL := 0.5;  // Гистерезис уставок, инж. ед.
    substitute : REAL := 0.0;  // Значение при неисправности канала
    simulation : BOOL;  // Режим имитации
    simValue : REAL;  // Значение имитации, инж. ед.
END_VAR
VAR_OUTPUT
    value : REAL;  // Значение, инж. ед.
    valid : BOOL;  // Значение достоверно
    channelFault : BOOL;  // Неисправность канала: обрыв, КЗ, переполнение
    overrange : BOOL;  // Выше номинала (27649...32511)
    underrange : BOOL;  // Ниже номинала (-4864...-1)
    alarmHH : BOOL;  // Аварийно высокое
    warnH : BOOL;  // Предупредительно высокое
    warnL : BOOL;  // Предупредительно низкое
    alarmLL : BOOL;  // Аварийно низкое
    statusWord : WORD;  // Слово состояния для HMI
END_VAR
VAR_TEMP
    rawClamped : INT;
    normalized : REAL;
END_VAR
VAR CONSTANT
    RAW_NOMINAL_LOW : INT := 0;
    RAW_NOMINAL_HIGH : INT := 27648;
    RAW_OVERSHOOT_MAX : INT := 32511;
    RAW_UNDERSHOOT_MIN : INT := -4864;
END_VAR
