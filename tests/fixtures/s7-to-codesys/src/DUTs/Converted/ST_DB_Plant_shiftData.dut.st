// Назначение: структура поля «shiftData» блока «DB_Plant» (анонимный Struct в SCL)
// Автор:      s7conv 0.1.0 (сгенерировано)
// Версия:     не указана
// Документ:   docs/MAPPING.md, раздел «Типы»
// Источник:   samples/scl/DB_Plant.scl, DATA_BLOCK "DB_Plant"
TYPE ST_DB_Plant_shiftData :
STRUCT
    // Данные смены
    startedAt : DT;  // Начало смены
    volume : LREAL;  // Объём за смену, м3
    pumpStarts : DINT;  // Пуски насосов за смену
END_STRUCT
END_TYPE
