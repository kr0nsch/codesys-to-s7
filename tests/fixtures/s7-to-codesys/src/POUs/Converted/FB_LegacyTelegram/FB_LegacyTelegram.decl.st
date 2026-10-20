// Назначение: Legacy telegram packer
//             Перенесён из STEP 7 V5.5 без переработки
// Автор:      WTP1 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     3.4 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_LegacyTelegram.scl, строки 36–131, FUNCTION_BLOCK "FB_LegacyTelegram", FAMILY Comm
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// MIGRATION-CHECK: стандартный (неоптимизированный) доступ S7: абсолютная адресация и порядок байтов не переносятся
//                  (стр. 36)
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_LegacyTelegram.scl
// Блок:   FUNCTION_BLOCK "FB_LegacyTelegram"
// -----------------------------------------------------------------------------
// Назначение
//   Упаковка телеграммы для удалённой станции (обмен через коммуникационный
//   процессор старой S7-300). Блок перенесён из STEP 7 V5.x без переработки и
//   оставлен неоптимизированным (S7_Optimized_Access := 'FALSE').
//   Экземпляр DB_LegacyTlg, буфер — DB_Telegram (DB30), архив — DB40.
//   Блок НАМЕРЕННО собран из конструкций, которые автоматически не переносятся:
//   AT-наложения, ANY-указатель и его разбор через AT-структуру, BLKMOV с
//   P#-указателем, абсолютная адресация %DB30.DBW0, косвенная адресация
//   WORD_TO_BLOCK_DB(...).DW[...], таймер S5 (S_ODT с номером таймера),
//   GOTO и метки, ENO. Ожидаемый результат конвертации — MIGRATION-TODO
//   с причиной по каждой конструкции; перенос — ручной, по описанию ниже.
//
// Логика (для ручного переноса)
//   1. По фронту send (память sendMem) телеграмма формируется, иначе выход
//      (GOTO lblExit), done := FALSE.
//   2. Длина области source берётся из ANY-указателя (поле length
//      AT-структуры). Больше 16 байт -> error := TRUE, ENO := FALSE, выход.
//   3. BLKMOV копирует source в DB30, байты 4...19; retVal — код BLKMOV.
//   4. Заголовок: %DB30.DBW0 := statusWord, %DB30.DBW2 := номер телеграммы
//      (seqNo + 1).
//   5. Если в statusWord бит 3 (авария станции) — слово дублируется в архив
//      WORD_TO_BLOCK_DB(archiveDb).DW[0]; биты разбираются через AT-наложение
//      массива Bool на копию слова.
//   6. Ошибка BLKMOV -> error, ENO := FALSE, переход к повтору; без ошибки
//      done := TRUE, retries := 0.
//   7. Повтор: S_ODT (таймер "T_Retry" = T5, задержка retryDelay в S5Time);
//      по истечении — retries + 1 (не больше 3) и сброс sendMem, чтобы
//      следующий вызов с send = TRUE повторил отправку.
// =============================================================================
FUNCTION_BLOCK FB_LegacyTelegram
VAR_INPUT
    send : BOOL;  // Отправить (по фронту)
    statusWord : WORD;  // Слово состояния станции
    // MIGRATION-TODO: Any (указатель S7) — нет аналога (стр. 47)
    // source : Any;
    archiveDb : INT;  // Номер DB архива
    // MIGRATION-CHECK: S5Time → TIME: в S7 S5TIME — BCD с шагом 10 мс…10 с, диапазон до 2h46m30s (стр. 49)
    retryDelay : TIME := T#2S;  // Задержка повтора
END_VAR
VAR_OUTPUT
    done : BOOL;  // Телеграмма сформирована
    error : BOOL;  // Ошибка
    retVal : INT;  // Код возврата BLKMOV
    retries : INT;  // Число повторов
END_VAR
VAR
    seqNo : INT;  // Номер телеграммы
    statusCopy : WORD;  // Копия слова состояния
    // MIGRATION-TODO: AT (наложение переменных S7) — переписать через UNION или битовый доступ (стр. 62)
    // statusBits AT statusCopy : Array[0..15] of Bool;
    sendMem : BOOL;  // Память фронта send
END_VAR
VAR_TEMP
    // MIGRATION-TODO: Any (указатель S7) — нет аналога (стр. 67)
    // srcPtr : Any;
    // MIGRATION-TODO: AT (наложение переменных S7) — переписать через UNION или битовый доступ (стр. 68)
    // srcView AT srcPtr : Struct   // Разбор ANY: 10 байт
    //    syntaxId : Byte;
    //    dataType : Byte;
    //    length : Int;
    //    dbNumber : Int;
    //    areaPointer : DWord;
    // END_STRUCT;
    // MIGRATION-CHECK: S5Time → TIME: в S7 S5TIME — BCD с шагом 10 мс…10 с, диапазон до 2h46m30s (стр. 75)
    remaining : TIME;
    retryElapsed : BOOL;
    timerValue : WORD;
END_VAR
