// Назначение: таймер задержки выключения с интерфейсом TOF (IN, PT, Q, ET) для кода, сконвертированного
//             s7conv из S7 TOF_TIME/TOF с --timers s7compat. Семантика МЭК 61131-3 и S7: при IN = TRUE
//             Q = TRUE и ET = 0; отсчёт идёт с вызова, на котором IN стал FALSE; Q = FALSE, когда
//             прошло >= PT (тогда ET = PT); если IN вернулся раньше, Q не падал. До первого TRUE на IN
//             Q = FALSE. Время — F_S7Now(): в работе TIME(), как у Standard.TOF, в тестах —
//             моделируемые часы GVL_S7Clock. Совпадение со Standard.TOF в реальном времени — тест
//             FB_S7Tof_Test.MatchesStandardInRealTime.
// Автор:      kr0nsch
// Версия:     0.1.0
// Документ:   docs/MAPPING.md, раздел «Функциональные блоки инструкций»; docs/methodology.md
FUNCTION_BLOCK FB_S7Tof
VAR_INPUT
    IN : BOOL;          // lint:allow STL007 интерфейс TOF: имя входа как у Standard.TOF
    PT : TIME;          // lint:allow STL007 интерфейс TOF: заданное время
END_VAR
VAR_OUTPUT
    Q : BOOL;           // lint:allow STL007 интерфейс TOF: выход с задержкой выключения
    ET : TIME;          // lint:allow STL007 интерфейс TOF: прошедшее время
END_VAR
VAR
    xInPrev : BOOL;     // IN на прошлом вызове (FALSE до первого вызова)
    xRunning : BOOL;    // идёт отсчёт задержки выключения
    tNow : TIME;        // время этого вызова (F_S7Now читается один раз)
    tStart : TIME;      // момент, когда IN стал FALSE
    tElapsed : TIME;    // прошло с tStart
END_VAR
