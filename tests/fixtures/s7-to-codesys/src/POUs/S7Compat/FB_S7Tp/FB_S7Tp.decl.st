// Назначение: импульсный таймер с интерфейсом TP (IN, PT, Q, ET) для кода, сконвертированного s7conv
//             из S7 TP_TIME/TP с --timers s7compat. Семантика МЭК 61131-3 и S7: фронт IN вне импульса
//             запускает импульс Q длительностью PT; фронты во время импульса его не продлевают; ET
//             растёт до PT во время импульса, после импульса остаётся PT, пока IN = TRUE, и
//             сбрасывается в 0 при IN = FALSE. Время — F_S7Now(): в работе TIME(), как у Standard.TP,
//             в тестах — моделируемые часы GVL_S7Clock. Совпадение со Standard.TP в реальном времени —
//             тест FB_S7Tp_Test.MatchesStandardInRealTime.
// Автор:      kr0nsch
// Версия:     0.1.0
// Документ:   docs/MAPPING.md, раздел «Функциональные блоки инструкций»; docs/methodology.md
FUNCTION_BLOCK FB_S7Tp
VAR_INPUT
    IN : BOOL;          // lint:allow STL007 интерфейс TP: имя входа как у Standard.TP
    PT : TIME;          // lint:allow STL007 интерфейс TP: длительность импульса
END_VAR
VAR_OUTPUT
    Q : BOOL;           // lint:allow STL007 интерфейс TP: импульс
    ET : TIME;          // lint:allow STL007 интерфейс TP: прошедшее время импульса
END_VAR
VAR
    xInPrev : BOOL;     // IN на прошлом вызове (FALSE до первого вызова)
    tNow : TIME;        // время этого вызова (F_S7Now читается один раз)
    tStart : TIME;      // начало импульса
    tElapsed : TIME;    // прошло с tStart
END_VAR
