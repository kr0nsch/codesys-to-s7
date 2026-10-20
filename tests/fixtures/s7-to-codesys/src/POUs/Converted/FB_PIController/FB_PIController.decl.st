// Назначение: Simple PI controller
//             ПИ-регулятор давления, антинасыщение ограничением интегратора
// Автор:      WTP2 (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     1.0 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/FB_PIController.scl, строки 30–118, FUNCTION_BLOCK "FB_PIController", FAMILY Control
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   FB_PIController.scl
// Блок:   FUNCTION_BLOCK "FB_PIController"
// -----------------------------------------------------------------------------
// Назначение
//   Простой ПИ-регулятор давления в коллекторе (выход — задание частоты ПЧ
//   ведущего насоса, %). Вызывается в OB "Cyclic interrupt" с периодом cycleTime.
//   Экземпляр DB_PIC101. Это не замена PID_Compact: без самонастройки и
//   без D-составляющей.
//
// Логика (нормативное описание; один вызов = один период cycleTime)
//   1. e := sp - pv при reverseActing = TRUE (насос: давление ниже уставки —
//      увеличить частоту); e := pv - sp при reverseActing = FALSE.
//      Если |e| < deadband: e := 0.
//   2. dt := cycleTime в секундах; tiS := ti в секундах.
//   3. manual = TRUE: outPercent := LIMIT(outMin, manValue, outMax);
//      integral := outPercent - kp * e (безударный переход в авто).
//   4. manual = FALSE: если tiS > 0: integral := integral + kp * e * dt / tiS,
//      иначе integral := 0; затем integral ограничивается так, чтобы
//      kp * e + integral лежало в outMin...outMax (антинасыщение ограничением);
//      outPercent := LIMIT(outMin, kp * e + integral, outMax).
//   5. atHighLimit / atLowLimit — outPercent на границе; errorOut := e.
//   integral хранится в LReal.
// Что проверяет при конвертации
//   LReal и смешанная арифметика с Real, ABS, LIMIT, MAX/MIN с именованными
//   параметрами IN1/IN2, TIME_TO_DINT, ветвление IF/ELSE, VAR CONSTANT.
// =============================================================================
FUNCTION_BLOCK FB_PIController
VAR_INPUT
    sp : REAL;  // Уставка, бар
    pv : REAL;  // Измеренное значение, бар
    kp : REAL := 1.0;  // Коэффициент усиления, %/бар
    ti : TIME := T#10S;  // Время интегрирования
    deadband : REAL := 0.02;  // Зона нечувствительности, бар
    reverseActing : BOOL := TRUE;  // Обратное действие (e = sp - pv)
    outMin : REAL := 0.0;  // Нижний предел выхода, %
    outMax : REAL := 100.0;  // Верхний предел выхода, %
    manual : BOOL;  // Ручной режим
    manValue : REAL;  // Ручное значение выхода, %
    cycleTime : TIME := T#100MS;  // Период вызова
END_VAR
VAR_OUTPUT
    outPercent : REAL;  // Выход регулятора, %
    errorOut : REAL;  // Рассогласование после зоны нечувствительности
    atHighLimit : BOOL;  // Выход на верхнем пределе
    atLowLimit : BOOL;  // Выход на нижнем пределе
END_VAR
VAR
    integral : LREAL;  // Интегральная составляющая, %
END_VAR
VAR_TEMP
    e : REAL;
    dtSeconds : LREAL;
    tiSeconds : LREAL;
    pPart : LREAL;
    upper : LREAL;
    lower : LREAL;
END_VAR
VAR CONSTANT
    MS_PER_SECOND : LREAL := 1000.0;
END_VAR
