// Назначение: Dosing pulse and batch counter
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_BatchCounter.scl, строки 29–94, FUNCTION_BLOCK "FB_BatchCounter", FAMILY Dosing
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_BatchCounter.scl
// Блок:   FUNCTION_BLOCK "FB_BatchCounter"
// -----------------------------------------------------------------------------
// Назначение
//   Счёт доз реагента: импульсный расходомер дозирующего насоса даёт импульс
//   на каждые 10 мл; pulsesPerDose импульсов — одна доза; batchPreset доз —
//   партия (сигнал на смену бака). Экземпляр DB_Dosing.
//
// Логика (нормативное описание)
//   1. Импульс считается по спаду pulseInput (F_TRIG; контакт геркона
//      нормально замкнутый). reset (уровень) обнуляет счёт импульсов и счётчик доз.
//   2. pulseCounter := pulseCounter + 1 на каждый импульс; при
//      pulseCounter >= pulsesPerDose: doseDone (импульс на вызов) := TRUE,
//      pulseCounter := 0.
//   3. Счётчик доз — CTU_INT (CU := doseDone, R := reset, PV := batchPreset):
//      doseCount := CV, batchDone := Q.
//   4. statusByte: бит 0 — batchDone, бит 1 — счёт идёт (pulseCounter > 0),
//      бит 2 — pulsesPerDose <= 0 (ошибка параметра), биты 3...7 = 0.
//   5. packedCounters (DWord): старшее слово — doseCount, младшее — pulseCounter
//      (SHL на 16 и OR). lowWordCopy := packedCounters.%W0 (младшее слово),
//      highByteOfLow := lowWordCopy.%B1 (обращение к срезам).
// Что проверяет при конвертации
//   CTU_INT (в CODESYS у CTU вход RESET и тип WORD — нужна проверка), F_TRIG,
//   Byte/Word/DWord, SHL, OR, INT_TO_WORD, WORD_TO_DWORD, срезы .%Xn/.%Wn/.%Bn.
// =============================================================================
FUNCTION_BLOCK FB_BatchCounter
VAR_INPUT
    pulseInput : BOOL;  // Импульсы расходомера реагента (НЗ контакт)
    reset : BOOL;  // Сброс счёта (уровень)
    pulsesPerDose : INT := 100;  // Импульсов на одну дозу
    batchPreset : INT := 20;  // Доз в партии
END_VAR
VAR_OUTPUT
    doseDone : BOOL;  // Доза набрана (один вызов)
    doseCount : INT;  // Число доз в партии
    batchDone : BOOL;  // Партия набрана
    statusByte : BYTE;  // Состояние для HMI
    packedCounters : DWORD;  // Счётчики одним словом для верхнего уровня
    lowWordCopy : WORD;  // Младшее слово packedCounters
    highByteOfLow : BYTE;  // Старший байт младшего слова
END_VAR
VAR
    pulseCounter : INT;  // Импульсы текущей дозы
    // MIGRATION-CHECK: F_TRIG: в S7 на первом вызове с CLK = FALSE спада нет; у F_TRIG CODESYS Standard 3.5.17.0 —
    //                  тоже (тест StandardFTrigMatchesS7 в Control Win); с другой версией Standard повторить этот
    //                  тест (стр. 54)
    edgePulse : F_TRIG;
    // MIGRATION-CHECK: счётчик S7 → CTU (CODESYS Standard): PV и CV — WORD (0…65535), в S7 — тип счётчика;
    //                  проверить диапазон (стр. 55)
    ctuBatch : CTU;
END_VAR
