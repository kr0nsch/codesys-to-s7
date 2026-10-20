// Назначение: Тип (UDT) «UDT_DosingRecipe», сконвертирован из SCL
// Автор:      не указан (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.2 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/UDT_PlantTypes.scl, строки 52–64, TYPE "UDT_DosingRecipe"
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
TYPE UDT_DosingRecipe :
STRUCT
    name : STRING(20) := 'DEFAULT';  // Имя рецепта
    reagent : INT := 1;  // 1 — коагулянт, 2 — флокулянт, 3 — гипохлорит
    doseStep : ARRAY[1..4] OF REAL := [0.5, 1.0, 1.5, 2.0];  // Доза по ступеням расхода, мг/л
    stepFlow : ARRAY[1..4] OF REAL := [4(0.0)];  // Границы ступеней расхода, м3/ч (задаются с HMI)
    contactTime : TIME := T#15M;  // Время контакта
    changedAt : DT := DT#2024-01-01-00:00:00;  // Когда изменён
    approved : BOOL;  // Утверждён технологом
END_STRUCT
END_TYPE
