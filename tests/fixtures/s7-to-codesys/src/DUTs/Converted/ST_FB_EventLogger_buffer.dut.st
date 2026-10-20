// Назначение: структура поля «buffer» блока «FB_EventLogger» (анонимный Struct в SCL)
// Автор:      s7conv 0.1.0 (сгенерировано)
// Версия:     не указана
// Документ:   docs/MAPPING.md, раздел «Типы»
// Источник:   samples/scl/FB_EventLogger.scl, FUNCTION_BLOCK "FB_EventLogger"
TYPE ST_FB_EventLogger_buffer :
STRUCT
    // Кольцевой буфер
    stamp : DT;
    code : INT;
    aux : INT;
    text : STRING(20);
END_STRUCT
END_TYPE
