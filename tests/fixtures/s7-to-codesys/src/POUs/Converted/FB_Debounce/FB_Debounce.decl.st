// Назначение: Debounce filter
//             Фильтр дребезга с задержками в S5Time
// Автор:      WTP1 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Debounce.scl, строки 27–79, FUNCTION_BLOCK "FB_Debounce", FAMILY Signals
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_Debounce.scl
// Блок:   FUNCTION_BLOCK "FB_Debounce"
// -----------------------------------------------------------------------------
// Назначение
//   Фильтр дребезга дискретного сигнала (поплавок, концевик). Блок перенесён со
//   старой S7-300: задержки по-прежнему задаются в S5Time и переводятся в Time
//   функцией S5TI_TIM. Экземпляр DB_LS201 (поплавок «фильтр опорожнён»),
//   мультиэкземпляры в FB_Valve (концевики задвижки).
//
// Логика (нормативное описание)
//   1. signal := raw XOR invert (invert = TRUE для нормально замкнутого контакта).
//   2. onDelay := S5TI_TIM(onDelayS5), offDelay := S5TI_TIM(offDelayS5).
//   3. debounced := TOF_TIME(IN := TON_TIME(IN := signal, PT := onDelay).Q,
//                            PT := offDelay).Q
//      — TRUE после onDelay непрерывного signal = TRUE; FALSE через offDelay после
//      того, как выход задержки включения стал FALSE.
//   4. rising / falling — импульс на один вызов по фронту / спаду debounced
//      (R_TRIG / F_TRIG); changeCount (UDInt) — число смен debounced.
// Что проверяет при конвертации
//   S5Time и литералы S5T# -> TIME с пометкой о точности S5Time (шаг 10 мс...10 с);
//   S5TI_TIM (нет в CODESYS: преобразование не нужно, если тип стал TIME);
//   TOF_TIME, F_TRIG, UDInt, XOR.
// =============================================================================
FUNCTION_BLOCK FB_Debounce
VAR_INPUT
    raw : BOOL;  // Сигнал с входа
    invert : BOOL;  // Инверсия (НЗ контакт)
    // MIGRATION-CHECK: S5Time → TIME: в S7 S5TIME — BCD с шагом 10 мс…10 с, диапазон до 2h46m30s (стр. 37)
    onDelayS5 : TIME := T#200MS;  // Задержка включения
    // MIGRATION-CHECK: S5Time → TIME: в S7 S5TIME — BCD с шагом 10 мс…10 с, диапазон до 2h46m30s (стр. 38)
    offDelayS5 : TIME := T#500MS;  // Задержка выключения
END_VAR
VAR_OUTPUT
    debounced : BOOL;  // Отфильтрованный сигнал
    rising : BOOL;  // Фронт debounced (один вызов)
    falling : BOOL;  // Спад debounced (один вызов)
    changeCount : UDINT;  // Число смен состояния
END_VAR
VAR
    tonOn : FB_S7Ton;
    tofOff : FB_S7Tof;
    edgeUp : R_TRIG;
    // MIGRATION-CHECK: F_TRIG: в S7 на первом вызове с CLK = FALSE спада нет; у F_TRIG CODESYS Standard 3.5.17.0 —
    //                  тоже (тест StandardFTrigMatchesS7 в Control Win); с другой версией Standard повторить этот
    //                  тест (стр. 52)
    edgeDown : F_TRIG;
END_VAR
VAR_TEMP
    signal : BOOL;
    onDelay : TIME;
    offDelay : TIME;
END_VAR
