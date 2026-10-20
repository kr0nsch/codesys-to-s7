// Назначение: Legacy telegram buffer
//             Буфер телеграммы удалённой станции (раскладка байтов фиксирована: DBW0 заголовок, DBW2 номер,
//             DBB4...19 данные)
// Автор:      WTP1 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/DB_Plant.scl, строки 111–131, DATA_BLOCK "DB_Telegram", FAMILY Comm
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// MIGRATION-CHECK: стандартный (неоптимизированный) доступ S7: абсолютная адресация и порядок байтов не переносятся
//                  (стр. 111)
{attribute 'qualified_only'}
VAR_GLOBAL
    header : WORD;  // DBW0: слово состояния станции
    seqNo : WORD;  // DBW2: номер телеграммы
    payload : ARRAY[0..15] OF BYTE;  // DBB4...DBB19: данные
    crc : WORD;  // DBW20
    reserve : ARRAY[0..12] OF BYTE;  // DBB22...DBB34
    heartbeat : BYTE;  // DBB35: счётчик жизни (пишет POKE в FB_EventLogger)
END_VAR
