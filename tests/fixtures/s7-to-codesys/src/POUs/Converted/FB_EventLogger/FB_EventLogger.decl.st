// Назначение: Event ring buffer
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.9 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_EventLogger.scl, строки 31–134, FUNCTION_BLOCK "FB_EventLogger", FAMILY Diag
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_EventLogger.scl
// Блок:   FUNCTION_BLOCK "FB_EventLogger"
// -----------------------------------------------------------------------------
// Назначение
//   Журнал событий станции в кольцевом буфере на 16 записей с отметкой времени
//   CPU, плюс служебные действия со «старым» неоптимизированным DB_Telegram
//   (номер DB30): чтение байта состояния через PEEK и запись счётчика жизни
//   через POKE. Экземпляр DB_Logger.
//   Блок НАМЕРЕННО содержит конструкции S7-1500 без прямого аналога в
//   CODESYS Standard: Variant/TypeOf/VariantGet, RD_SYS_T, RUNTIME, PEEK/POKE.
//   Ожидаемый результат конвертации — MIGRATION-TODO с причиной, а не тихий перевод.
//
// Логика (нормативное описание)
//   1. execTime := RUNTIME(runtimeMem) — время между вызовами, с (LReal).
//   2. clear = TRUE: коды и тексты всех записей := 0 / '', writeIndex := 0.
//   3. Новое событие — eventCode <> 0 и eventCode <> код прошлого вызова:
//      отметка времени RD_SYS_T (ошибка -> error := TRUE);
//      текст := 'E:' + первые 18 символов eventText (CONCAT, LEFT);
//      если extraInfo имеет тип Int — его значение пишется в поле aux записи;
//      запись в buffer[writeIndex], writeIndex := (writeIndex + 1) MOD 16.
//   4. entries — число записей подряд с начала буфера с кодом <> 0
//      (WHILE с EXIT на первой пустой).
//   5. telegramStatus := PEEK(DB30, байт 0); heartbeat + 1 -> POKE(DB30, байт 35).
// Что проверяет при конвертации
//   массив анонимных структур, MOD, WHILE/EXIT, строковые функции; честный
//   отказ на Variant, системных функциях и прямом доступе к памяти.
// =============================================================================
FUNCTION_BLOCK FB_EventLogger
VAR_INPUT
    eventCode : INT;  // Код события (0 — нет события)
    eventText : STRING(20);  // Текст события
    // MIGRATION-TODO: Variant — нет аналога в CODESYS; переписать (ANY, POINTER или перегрузка) (стр. 40)
    // extraInfo : Variant;
    clear : BOOL;  // Очистить журнал
END_VAR
VAR_OUTPUT
    entries : INT;  // Число записей в журнале
    lastStamp : DT;  // Время последней записи
    telegramStatus : BYTE;  // Байт состояния телеграммы (DB_Telegram.DBB0)
    execTime : LREAL;  // Время между вызовами, с
    error : BOOL;  // Ошибка чтения часов
END_VAR
VAR
    buffer : ARRAY[0..15] OF ST_FB_EventLogger_buffer;
    writeIndex : INT;  // Куда писать следующую запись
    lastCode : INT;  // Код прошлого вызова
    heartbeat : BYTE;  // Счётчик жизни
    runtimeMem : LREAL;  // Память для RUNTIME
END_VAR
VAR_TEMP
    nowDt : DT;
    // MIGRATION-CHECK: имя «ret» переименовано в «ret_» (ключевое слово CODESYS или повтор) (стр. 67)
    ret_ : INT;
    i : INT;
    extraInt : INT;
    msg : STRING(20);
END_VAR
VAR CONSTANT
    BUFFER_SIZE : INT := 16;
    TELEGRAM_DB : UINT := 30;
    AREA_DB : BYTE := 16#84;
END_VAR
