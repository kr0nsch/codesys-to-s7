// Назначение: Complete Restart
// Автор:      не указан (исходный блок S7); перевод в ST — s7conv 0.1.0
// Версия:     0.1 (исходный блок S7)
// Документ:   docs/CONVERSION_REPORT.md, docs/MAPPING.md
// Источник:   samples/scl/OB_Startup.scl, строки 32–65, ORGANIZATION_BLOCK "Startup"
// Сгенерировано s7conv: пометки MIGRATION-CHECK и MIGRATION-TODO требуют ручного разбора.
// MIGRATION-CHECK: OB100 (Startup) → однократное выполнение по флагу первого цикла в MainTask: флаг (не RETAIN)
//                  сбрасывается загрузкой, Reset warm/cold и перезапуском ПЛК, но не командой Stop → Start CODESYS
//                  (в S7 OB100 выполняется при каждом STOP → RUN); задачи с более высоким приоритетом могут
//                  выполниться раньше (стр. 32)
// MIGRATION-CHECK: входы OB (стартовая информация S7) объявлены как VAR — CODESYS их не заполняет (стр. 36)
// ---- комментарий в начале исходного файла SCL ----
// =============================================================================
// s7-to-codesys — корпус SCL. Написан с нуля, объект вымышленный (ВОС «Северная»).
//
// Файл:   OB_Startup.scl
// Блоки:  ORGANIZATION_BLOCK "Startup" (OB100, запуск),
//         ORGANIZATION_BLOCK "Diagnostic error interrupt" (OB82)
// -----------------------------------------------------------------------------
// Назначение
//   "Startup": инициализация после перехода CPU в RUN — режим станции, слово
//   команд HMI; при потере сохраняемых данных — обнуление накопленных величин;
//   при потере часов — установка времени по умолчанию (WR_SYS_T, тип DTL).
//   "Diagnostic error interrupt": счётчик диагностических событий модулей и
//   последние HW-идентификатор, канал, IO_State.
//   Состав входов OB (LostRetentive, LostRTC; IO_State, LADDR, Channel,
//   MultiError) приведён по памяти — сверить с документацией TIA Portal.
//
// Логика (нормативное описание)
//   Startup:
//     1. plantMode := 0, cmdWord := 0, modeRequest := -1.
//     2. LostRetentive: totalVolume := 0, backwashCount := 0,
//        filterRuntime[1..4] := T#0MS.
//     3. LostRTC: clockLost := TRUE, WR_SYS_T(defaultClock).
//   Diagnostic error interrupt:
//     diagCount + 1; diagLastLaddr := LADDR; diagLastChannel := Channel;
//     diagIoState := IO_State.
// Что проверяет при конвертации
//   OB100 -> код инициализации (в CODESYS нет OB запуска: флаг первого цикла,
//   FB_init или системное событие — решение вручную); OB82 и HW_ANY — без
//   аналога (диагностика в CODESYS через драйверы/IoDrv — ручная работа);
//   WR_SYS_T и DTL — системные, MIGRATION-TODO.
// =============================================================================
PROGRAM PRG_Startup
VAR
    LostRetentive : BOOL;  // TRUE, если сохраняемые данные потеряны
    LostRTC : BOOL;  // TRUE, если часы реального времени потеряны
END_VAR
VAR_TEMP
    i : INT;
    // MIGRATION-CHECK: имя «ret» переименовано в «ret_» (ключевое слово CODESYS или повтор) (стр. 43)
    ret_ : INT;
END_VAR
VAR
    xS7convStartupDone : BOOL; // флаг первого цикла (замена OB100)
END_VAR
