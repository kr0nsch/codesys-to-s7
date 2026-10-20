// Назначение: структура поля «limits» блока «UDT_AnalogCfg» (анонимный Struct в SCL)
// Автор:      s7conv 0.1.0 (сгенерировано)
// Версия:     не указана
// Документ:   docs/MAPPING.md, раздел «Типы»
// Источник:   samples/scl/UDT_PlantTypes.scl, TYPE "UDT_AnalogCfg"
TYPE ST_UDT_AnalogCfg_limits :
STRUCT
    // Уставки сигнализации, инж. ед.
    hh : REAL := 14.0;  // Аварийно высокое
    h : REAL := 12.0;  // Предупредительно высокое
    l : REAL := 2.0;  // Предупредительно низкое
    ll : REAL := 1.0;  // Аварийно низкое
END_STRUCT
END_TYPE
