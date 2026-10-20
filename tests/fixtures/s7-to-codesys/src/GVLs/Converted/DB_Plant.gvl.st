// Назначение: Plant process data
//             Технологические данные станции II подъёма
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.3 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/DB_Plant.scl, строки 29–79, DATA_BLOCK "DB_Plant", FAMILY Plant
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   DB_Plant.scl
// Блоки:  глобальные DB "DB_Plant", "DB_Hmi", "DB_Telegram";
//         DB по типу UDT "DB_RecipeActive";
//         экземплярные DB функциональных блоков (18 шт.).
// -----------------------------------------------------------------------------
// Назначение
//   Все блоки данных станции в одном исходнике («Generate source from blocks»
//   для группы DB). Логики нет, кроме начальных значений в секции BEGIN.
//   DB_Plant        — технологические данные; часть переменных сохраняемая
//                     (секция VAR RETAIN): объём за всё время, наработка
//                     фильтров, число промывок.
//   DB_Hmi          — интерфейс с панелью оператора: команды, уставки, текст.
//   DB_Telegram     — неоптимизированный DB (S7_Optimized_Access := 'FALSE')
//                     с фиксированной раскладкой байтов: к нему обращаются
//                     абсолютно (%DB30.DBW0, P#DB30.DBX4.0) и через PEEK/POKE.
//                     Номер DB30 — свойство блока, в исходник TIA не попадает
//                     (см. BlockProperties.csv).
//   DB_RecipeActive — DB, созданный по типу "UDT_DosingRecipe". По тексту его
//                     не отличить от экземплярного DB: нужна таблица символов.
//   Экземплярные DB записаны в двух формах: как выгружает TIA Portal (имя ФБ
//   отдельной строкой после NON_RETAIN) и компактно (DATA_BLOCK "DB" "FB").
// Что проверяет при конвертации
//   DB -> GVL; RETAIN -> RETAIN/PERSISTENT; экземплярный DB -> экземпляр ФБ в GVL;
//   начальные значения из BEGIN; массив UDT; DTL (нет аналога в CODESYS Standard).
// =============================================================================
{attribute 'qualified_only'}
VAR_GLOBAL
    estopOk : BOOL;  // Аварийный стоп не нажат (копия %I0.0)
    tankLevel : REAL := 0.0;  // Уровень в РЧВ, м
    flowSamples : ARRAY[1..8] OF REAL;  // Выборка расхода FT101 раз в секунду, м3/ч
    flowMin : REAL;  // Минимум по выборке, м3/ч
    flowMax : REAL;  // Максимум по выборке, м3/ч
    flowAvg : REAL;  // Среднее по выборке, м3/ч
    flowSampleCount : INT;  // Число достоверных отсчётов в выборке
    clockMem : BOOL;  // Память фронта меркера тактов "Clock_1Hz"
    pressureCfg : UDT_AnalogCfg := (rangeHigh := 16.0);  // Параметры канала PT101 для HMI
    pumpStatus : ARRAY[1..3] OF UDT_DeviceStatus;  // Состояния насосов P101...P103
    plantMode : INT := 1;  // 0 — стоп, 1 — работа, 2 — промывка
    alarmWord : WORD;  // Слово аварий станции (биты см. OB "Main")
    alarmDWord : DWORD;  // Расширенное слово аварий
    heartbeat : BYTE;  // Счётчик жизни для верхнего уровня
    pressureFastRaw : INT;  // Давление PT101, прямое чтение периферии
    lastStart : DT;  // Время последнего пуска станции
    // MIGRATION-TODO: DTL — структура S7 (YEAR, MONTH, ...), в CODESYS нет; заменить на DT или свою структуру (стр.
    //                 53)
    // defaultClock { ExternalAccessible := 'False'; ExternalVisible := 'False'; ExternalWritable := 'False'} : DTL;
    clockLost : BOOL;  // Часы CPU потеряны при запуске
    diagCount : DINT;  // Число диагностических прерываний
    diagLastLaddr : WORD;  // Аппаратный идентификатор последнего модуля с диагностикой
    diagLastChannel : UINT;  // Канал последней диагностики
    diagIoState : WORD;  // IO_State последней диагностики
    operatorName : STRING(20) := 'NOBODY';  // Оператор смены
    shiftData : ST_DB_Plant_shiftData;
END_VAR
VAR_GLOBAL RETAIN
    totalVolume : LREAL;  // Объём за всё время, м3 (копия из DB_FQ101)
    filterRuntime : ARRAY[1..4] OF TIME;  // Наработка фильтров с последней промывки
    backwashCount : DINT;  // Число промывок
END_VAR
