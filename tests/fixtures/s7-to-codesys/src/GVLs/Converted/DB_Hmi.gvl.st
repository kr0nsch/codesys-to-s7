// Назначение: HMI interface
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.2 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/DB_Plant.scl, строки 81–109, DATA_BLOCK "DB_Hmi", FAMILY Hmi
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
{attribute 'qualified_only'}
VAR_GLOBAL
    cmdWord : WORD;  // Запросы режима (биты, см. FB_ModeSelect); ФБ сбрасывает обработанные биты
    modeRequest : INT := -1;  // Запрос режима числом: -1 — нет запроса
    pump : ARRAY[1..3] OF ST_DB_Hmi_pump;
    alarmAck : BOOL;  // Квитирование аварий
    backwashStart : BOOL;  // Пуск промывки фильтра
    backwashStop : BOOL;  // Прерывание промывки
    resetTotal : BOOL;  // Сброс сменного счётчика объёма
    setpointPressure : REAL := 4.5;  // Уставка давления в коллекторе, бар
    pidManual : BOOL;  // Ручной режим регулятора давления
    pidManualValue : REAL;  // Ручное задание частоты, %
    message : STRING(20);  // Текст для бегущей строки
END_VAR
