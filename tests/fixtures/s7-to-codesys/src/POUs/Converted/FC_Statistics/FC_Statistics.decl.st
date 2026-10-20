// Назначение: Min/max/average over 8 samples
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FC_Statistics.scl, строки 26–104, FUNCTION "FC_Statistics", FAMILY Math
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FC_Statistics.scl
// Блок:   FUNCTION "FC_Statistics" : Int
// -----------------------------------------------------------------------------
// Назначение
//   Скользящая выборка расхода (8 отсчётов) и статистика по ней: минимум,
//   максимум, среднее по достоверным отсчётам. Массив выборки передаётся как
//   VAR_IN_OUT и хранится в "DB_Plant".flowSamples (у FC нет своей памяти).
//
// Логика (нормативное описание)
//   1. Если validLow > validHigh: minValue, maxValue, average := 0.0,
//      возвращается -1, ENO не меняется (RETURN сразу).
//   2. Если shift = TRUE: samples[1..7] := samples[2..8], samples[8] := newSample.
//   3. Достоверный отсчёт — validLow <= samples[i] <= validHigh; остальные
//      пропускаются (CONTINUE).
//   4. По достоверным: minValue, maxValue, average (сумма в LReal / число).
//      Если достоверных нет: minValue = maxValue = average = 0.0.
//   5. Возвращаемое значение — число достоверных отсчётов 0...8.
// Что проверяет при конвертации
//   FUNCTION с типом результата и присваиванием #FC_Statistics := ...,
//   VAR_IN_OUT массива, FOR ... TO ... BY, CONTINUE, RETURN, MIN/MAX(IN1, IN2),
//   INT_TO_LREAL, LREAL_TO_REAL.
// =============================================================================
FUNCTION FC_Statistics : INT
VAR_INPUT
    newSample : REAL;  // Новый отсчёт
    shift : BOOL;  // Сдвинуть выборку и добавить newSample
    validLow : REAL;  // Нижняя граница достоверности
    validHigh : REAL;  // Верхняя граница достоверности
END_VAR
VAR_OUTPUT
    minValue : REAL;  // Минимум
    maxValue : REAL;  // Максимум
    average : REAL;  // Среднее
END_VAR
VAR_IN_OUT
    samples : ARRAY[1..8] OF REAL;  // Выборка (хранится у вызывающего)
END_VAR
VAR
    i : INT;
    count : INT;
    sum : LREAL;
END_VAR
VAR CONSTANT
    SAMPLE_COUNT : INT := 8;
END_VAR
