// Назначение: Diagnostic error interrupt
// Автор:      не указан (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/OB_Startup.scl, строки 67–85, ORGANIZATION_BLOCK "Diagnostic error interrupt"
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// MIGRATION-TODO: OB82: событийный OB — задача по событию не создаётся, настроить вручную (стр. 67)
// MIGRATION-CHECK: входы событийного OB (стартовая информация S7) оставлены VAR_INPUT: CODESYS их не заполняет — их
//                  передаёт вызов из обработчика события (стр. 71)
PROGRAM PRG_Diagnostic_error_interrupt
VAR_INPUT
    IO_State : WORD;  // Состояние ввода-вывода объекта
    // MIGRATION-TODO: системный тип S7 HW_ANY не поддерживается (стр. 73)
    // LADDR : HW_ANY;
    Channel : UINT;  // Номер канала
    MultiError : BOOL;  // TRUE, если ошибок несколько
END_VAR
