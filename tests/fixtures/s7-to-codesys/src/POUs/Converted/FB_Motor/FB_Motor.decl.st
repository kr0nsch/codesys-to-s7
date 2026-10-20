// Назначение: Motor with feedback monitoring
//             Насос прямого пуска: авто/ручной, контроль обратной связи, тепловая защита
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     2.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_Motor.scl, строки 41–157, FUNCTION_BLOCK "FB_Motor", FAMILY Drives
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_Motor.scl
// Блок:      FUNCTION_BLOCK "FB_Motor"
// Сценарии:  scenarios/FB_Motor.csv (модель scenarios/reference/model_fb_motor.py)
// -----------------------------------------------------------------------------
// Назначение
//   Управление нерегулируемым насосом (прямой пуск контактором): режимы авто и
//   ручной, контроль обратной связи по времени, тепловая защита, защёлка аварии
//   с кодом, счётчик пусков, состояние для HMI в "UDT_DeviceStatus".
//   Экземпляры: DB_P101, DB_P102, DB_P103 (насосы II подъёма).
//
// Логика (нормативное описание; порядок шагов внутри вызова важен)
//   Коды аварии: 0 — нет, 1 — нет обратной связи после пуска, 2 — обратная связь
//   пропала в работе, 3 — тепловая защита, 4 — обратная связь без команды.
//   Правило «первая авария»: код записывается, только если fault = FALSE.
//   1. Сброс: по фронту reset (R_TRIG), если thermalOk = TRUE:
//      fault := FALSE, код := 0.
//   2. Тепловая защита: если thermalOk = FALSE и fault = FALSE: fault := TRUE, код := 3.
//   3. Ручная защёлка manRun:
//        autoMode = TRUE:  manRun := autoStart (слежение: переход авто -> ручной безударный);
//        autoMode = FALSE: если manStop или fault -> manRun := FALSE,
//                          иначе если manStart -> manRun := TRUE, иначе без изменений.
//   4. demand := autoStart в авто, manRun в ручном; runCmd := demand AND NOT fault.
//   5. feedbackSeen := FALSE, если runCmd = FALSE; := TRUE, если runCmd и feedback;
//      иначе без изменений.
//   6. Рассогласование: TON_TIME (IN := runCmd XOR feedback, PT := feedbackTime).
//      Если Q = TRUE и fault = FALSE: fault := TRUE; код := 4, если runCmd = FALSE;
//      иначе 2, если feedbackSeen; иначе 1. В этом же вызове runCmd := FALSE.
//   7. startCount (DInt) увеличивается на 1 по фронту итогового runCmd (R_TRIG).
//   8. status: running := runCmd AND feedback; fault; autoMode := вход autoMode;
//      faultCode; startCount.
//   Сброс не снимает аварию 4, пока обратная связь без команды держится дольше
//   feedbackTime: таймер п. 6 остаётся в Q = TRUE и снова ставит аварию в том же вызове.
// Что проверяет при конвертации
//   TON_TIME/R_TRIG как мультиэкземпляры (атрибуты InstructionName/LibVersion),
//   вызов с переносом параметров на несколько строк, XOR, выход типа UDT,
//   локальные константы.
// =============================================================================
FUNCTION_BLOCK FB_Motor
VAR_INPUT
    autoMode : BOOL;  // TRUE — авто, FALSE — ручной
    autoStart : BOOL;  // Команда пуска от автоматики (уровень)
    manStart : BOOL;  // Пуск оператором в ручном режиме
    manStop : BOOL;  // Стоп оператором в ручном режиме, приоритет над пуском
    feedback : BOOL;  // Обратная связь «в работе» от контактора
    thermalOk : BOOL := TRUE;  // Тепловое реле в норме
    reset : BOOL;  // Сброс аварии (по фронту)
    feedbackTime : TIME := T#3S;  // Допустимое рассогласование команды и обратной связи
END_VAR
VAR_OUTPUT
    runCmd : BOOL;  // Команда на контактор
    fault : BOOL;  // Авария (защёлка)
    status : UDT_DeviceStatus;  // Состояние для HMI
END_VAR
VAR
    manRun : BOOL;  // Защёлка ручного пуска
    feedbackSeen : BOOL;  // Обратная связь была после подачи команды
    faultCode : INT;  // Код аварии
    startCount : DINT;  // Число пусков
    tonFeedback : FB_S7Ton;
    edgeReset : R_TRIG;
    edgeRun : R_TRIG;
END_VAR
VAR_TEMP
    demand : BOOL;
END_VAR
VAR CONSTANT
    FAULT_NONE : INT := 0;
    FAULT_NO_FEEDBACK : INT := 1;
    FAULT_FEEDBACK_LOST : INT := 2;
    FAULT_THERMAL : INT := 3;
    FAULT_UNEXPECTED_FEEDBACK : INT := 4;
END_VAR
