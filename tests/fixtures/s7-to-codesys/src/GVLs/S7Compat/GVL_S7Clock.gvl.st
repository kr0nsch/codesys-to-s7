// Назначение: источник времени слоя совместимости S7Compat для таймеров FB_S7Ton, FB_S7Tof, FB_S7Tp
//             (их вызывает код, сконвертированный s7conv с --timers s7compat). В рабочем приложении
//             xSimulation = FALSE, и F_S7Now() возвращает TIME() — время с запуска ПЛК, как у таймеров
//             CODESYS Standard. Тесты сценариев (tests/POUs/Scenarios) на время своего вызова включают
//             xSimulation и задают моделируемые часы tSimNow перед каждым вызовом блока, затем
//             выключают. В рабочем коде переменные не изменять.
// Автор:      kr0nsch
// Версия:     0.1.0
// Документ:   docs/methodology.md, раздел «Проверка поведения: время в тестах»
{attribute 'qualified_only'}
VAR_GLOBAL
    xSimulation : BOOL;     // TRUE — таймеры S7Compat идут по tSimNow (только тесты)
    tSimNow : TIME;         // моделируемые часы, мс от начала сценария
END_VAR
