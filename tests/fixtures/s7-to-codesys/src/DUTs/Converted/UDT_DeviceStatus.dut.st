// Назначение: Тип (UDT) «UDT_DeviceStatus», сконвертирован из SCL
// Автор:      не указан (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/UDT_PlantTypes.scl, строки 40–50, TYPE "UDT_DeviceStatus"
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
TYPE UDT_DeviceStatus :
STRUCT
    running : BOOL;  // Работает (команда и обратная связь)
    fault : BOOL;  // Авария (защёлка)
    autoMode : BOOL;  // Режим авто
    faultCode : INT;  // 0 — нет, 1 — нет ОС после пуска, 2 — пропала ОС, 3 — тепловая защита, 4 — ОС без команды
    startCount : DINT;  // Число пусков
END_STRUCT
END_TYPE
