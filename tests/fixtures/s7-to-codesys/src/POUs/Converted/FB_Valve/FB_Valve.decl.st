// Назначение: Motorized valve with travel monitoring
//             Задвижка: команды, концевики, контроль хода
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.2 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Valve.scl, строки 38–164, FUNCTION_BLOCK "FB_Valve", FAMILY Valves
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_Valve.scl
// Блок:   FUNCTION_BLOCK "FB_Valve"
// -----------------------------------------------------------------------------
// Назначение
//   Задвижка с электроприводом (открыть/закрыть, два концевика) с контролем
//   времени хода. Для пилотного бистабильного распределителя дополнительно
//   формируются импульсы pulseOpen/pulseClose. Экземпляр DB_XV201 (подача
//   исходной воды на фильтр).
//
// Логика (нормативное описание)
//   Состояния state: 0 — неизвестно, 1 — закрыта, 2 — открывается, 3 — открыта,
//   4 — закрывается, 9 — авария. Коды faultCode: 1 — не дошла за travelTime,
//   2 — оба концевика одновременно, 3 — самопроизвольный уход с концевика.
//   1. Концевики проходят через мультиэкземпляры "FB_Debounce" (задержки по
//      умолчанию): isOpen, isClosed.
//   2. По фронту reset (R_TRIG), если не оба концевика: state := 0, faultCode := 0.
//   3. Оба концевика (isOpen AND isClosed): state := 9, faultCode := 2 (сразу).
//   4. Таймеры хода: TON_TIME(IN := state = 2, PT := travelTime) и
//      TON_TIME(IN := state = 4, PT := travelTime) — вызываются до переходов.
//      Уход с концевика — спад isOpen / isClosed (F_TRIG).
//   5. Переходы (CASE state, один за вызов):
//        0: cmdClose -> 4; иначе cmdOpen -> 2; иначе isClosed -> 1; иначе isOpen -> 3;
//        1: cmdOpen AND NOT cmdClose -> 2; спад isClosed -> 9 (код 3);
//        2: cmdClose -> 4; isOpen -> 3; таймер открытия -> 9 (код 1);
//        3: cmdClose -> 4; спад isOpen -> 9 (код 3);
//        4: isClosed -> 1; cmdOpen AND NOT cmdClose -> 2; таймер закрытия -> 9 (код 1);
//        9: ожидание сброса; другое значение -> 0.
//   6. coilOpen := state = 2; coilClose := state = 4 (реверсивный пускатель);
//      pulseOpen / pulseClose — TP_TIME длиной pulseTime по входу в состояние 2 / 4.
// Что проверяет при конвертации
//   мультиэкземпляр пользовательского ФБ с типом в кавычках, обращение к его
//   выходу (#debOpen.debounced), TP_TIME, F_TRIG, CASE с несколькими операторами
//   в ветке, метки-литералы.
// =============================================================================
FUNCTION_BLOCK FB_Valve
VAR_INPUT
    cmdOpen : BOOL;  // Команда «открыть» (уровень)
    cmdClose : BOOL;  // Команда «закрыть» (уровень), приоритет над «открыть»
    limitOpen : BOOL;  // Концевик «открыто»
    limitClosed : BOOL;  // Концевик «закрыто»
    reset : BOOL;  // Сброс аварии (по фронту)
    travelTime : TIME := T#30S;  // Предельное время хода
    pulseTime : TIME := T#1S;  // Длительность импульса на пилот
END_VAR
VAR_OUTPUT
    coilOpen : BOOL;  // Пускатель «открыть»
    coilClose : BOOL;  // Пускатель «закрыть»
    pulseOpen : BOOL;  // Импульс «открыть» на пилот
    pulseClose : BOOL;  // Импульс «закрыть» на пилот
    isOpen : BOOL;  // Открыта (после фильтра)
    isClosed : BOOL;  // Закрыта (после фильтра)
    state : INT;  // Состояние
    faultCode : INT;  // Код аварии
END_VAR
VAR
    debOpen : FB_Debounce;  // Фильтр концевика «открыто»
    debClosed : FB_Debounce;  // Фильтр концевика «закрыто»
    tonOpening : FB_S7Ton;
    tonClosing : FB_S7Ton;
    tpOpen : FB_S7Tp;
    tpClose : FB_S7Tp;
    edgeReset : R_TRIG;
    // MIGRATION-CHECK: F_TRIG: в S7 на первом вызове с CLK = FALSE спада нет; у F_TRIG CODESYS Standard 3.5.17.0 —
    //                  тоже (тест StandardFTrigMatchesS7 в Control Win); с другой версией Standard повторить этот
    //                  тест (стр. 74)
    lostOpen : F_TRIG;
    // MIGRATION-CHECK: F_TRIG: в S7 на первом вызове с CLK = FALSE спада нет; у F_TRIG CODESYS Standard 3.5.17.0 —
    //                  тоже (тест StandardFTrigMatchesS7 в Control Win); с другой версией Standard повторить этот
    //                  тест (стр. 75)
    lostClosed : F_TRIG;
END_VAR
