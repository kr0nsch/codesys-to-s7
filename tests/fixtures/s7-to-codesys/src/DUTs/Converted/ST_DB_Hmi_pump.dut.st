// Назначение: структура поля «pump» блока «DB_Hmi» (анонимный Struct в SCL)
// Автор:      s7conv 0.1.0 (сгенерировано)
// Версия:     не указана
// Документ:   docs/MAPPING.md, раздел «Типы»
// Источник:   samples/scl/DB_Plant.scl, DATA_BLOCK "DB_Hmi"
TYPE ST_DB_Hmi_pump :
STRUCT
    // Команды насосам P101...P103
    startReq : BOOL;
    stopReq : BOOL;
    resetReq : BOOL;
END_STRUCT
END_TYPE
