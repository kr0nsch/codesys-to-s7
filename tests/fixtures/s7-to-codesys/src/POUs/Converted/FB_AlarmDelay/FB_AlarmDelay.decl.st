// Назначение: Alarm with delays and acknowledge
//             Сигнализация: задержка появления, задержка снятия, квитирование
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_AlarmDelay.scl, строки 30–109, FUNCTION_BLOCK "FB_AlarmDelay", FAMILY Alarms
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:      FB_AlarmDelay.scl
// Блок:      FUNCTION_BLOCK "FB_AlarmDelay"
// Сценарии:  scenarios/FB_AlarmDelay.csv (модель scenarios/reference/model_fb_alarm_delay.py)
// -----------------------------------------------------------------------------
// Назначение
//   Технологическая сигнализация с задержкой появления, задержкой снятия и
//   квитированием. Состояния в духе ISA-18.2 (норма, активна неквитирована,
//   активна квитирована, снята неквитирована). Экземпляр DB_AlarmPT101.
//
// Логика (нормативное описание; порядок шагов внутри вызова важен)
//   1. Фронт квитирования: R_TRIG(ack).
//   2. Задержка появления: TON_TIME (IN := condition AND enable, PT := onDelay).
//   3. Задержка снятия:    TOF_TIME (IN := выход Q таймера п. 2, PT := offDelay).
//      active := Q таймера п. 3 AND enable.
//   4. Если в этом вызове фронт квитирования: unacked := FALSE.
//   5. Фронт active (R_TRIG): unacked := TRUE, count := count + 1.
//      (Квитирование обрабатывается раньше: сигнал, появившийся в вызове с
//      фронтом ack, остаётся неквитированным.)
//   6. Если enable = FALSE: unacked := FALSE (сигнал выведен из работы).
//   7. alarm := active OR unacked.
//   8. state: 1 — active и unacked; 2 — active и NOT unacked;
//             3 — NOT active и unacked; 0 — иначе.
//   Начальное состояние экземпляра: все выходы FALSE / 0.
// Что проверяет при конвертации
//   TON_TIME + TOF_TIME в цепочке, R_TRIG по выходу самого ФБ, IF/ELSIF.
// =============================================================================
FUNCTION_BLOCK FB_AlarmDelay
VAR_INPUT
    condition : BOOL;  // Условие сигнала (без задержек)
    enable : BOOL := TRUE;  // Сигнал в работе
    ack : BOOL;  // Квитирование (по фронту)
    onDelay : TIME := T#5S;  // Задержка появления
    offDelay : TIME := T#2S;  // Задержка снятия
END_VAR
VAR_OUTPUT
    active : BOOL;  // Сигнал активен (с учётом задержек)
    unacked : BOOL;  // Требует квитирования
    alarm : BOOL;  // Индикация: активен или не квитирован
    state : INT;  // 0 — норма, 1 — активен/неквит., 2 — активен/квит., 3 — снят/неквит.
    count : DINT;  // Число появлений
END_VAR
VAR
    tonOn : FB_S7Ton;
    tofOff : FB_S7Tof;
    edgeAck : R_TRIG;
    edgeActive : R_TRIG;
END_VAR
VAR CONSTANT
    STATE_NORMAL : INT := 0;
    STATE_ACTIVE_UNACKED : INT := 1;
    STATE_ACTIVE_ACKED : INT := 2;
    STATE_CLEARED_UNACKED : INT := 3;
END_VAR
