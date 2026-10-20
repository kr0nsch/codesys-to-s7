// Назначение: таймер задержки включения с интерфейсом TON (IN, PT, Q, ET) для кода, сконвертированного
//             s7conv из S7 TON_TIME/TON с --timers s7compat. Семантика МЭК 61131-3 и S7: отсчёт идёт с
//             вызова, на котором IN стал TRUE (или с первого вызова, если IN уже TRUE); Q = IN И
//             (прошло >= PT) — на самом пороге Q уже TRUE; ET = MIN(прошло, PT) при IN = TRUE, иначе 0;
//             PT читается на каждом вызове. Время — F_S7Now(): в работе TIME(), как у Standard.TON, в
//             тестах — моделируемые часы GVL_S7Clock. Выходы меняются только при вызове.
//             «Прошло» копится по приращениям между вызовами (каждое — по модулю 2^32) и насыщается на
//             максимуме TIME: при IN = TRUE дольше 2^32 мс (около 49,7 суток) Q не падает, как у S7 и
//             Standard.TON (разность «сейчас − старт» после перехода TIME через ноль стала бы малой).
//             Совпадение со Standard.TON в реальном времени — тест FB_S7Ton_Test.MatchesStandardInRealTime.
// Автор:      kr0nsch
// Версия:     0.2.0
// Документ:   docs/MAPPING.md, раздел «Функциональные блоки инструкций»; docs/methodology.md
FUNCTION_BLOCK FB_S7Ton
VAR_INPUT
    IN : BOOL;          // lint:allow STL007 интерфейс TON: имя входа как у Standard.TON
    PT : TIME;          // lint:allow STL007 интерфейс TON: заданное время
END_VAR
VAR_OUTPUT
    Q : BOOL;           // lint:allow STL007 интерфейс TON: выход задержки
    ET : TIME;          // lint:allow STL007 интерфейс TON: прошедшее время
END_VAR
VAR
    xInPrev : BOOL;     // IN на прошлом вызове (FALSE до первого вызова)
    tNow : TIME;        // время этого вызова (F_S7Now читается один раз)
    tLast : TIME;       // время прошлого вызова
    tDelta : TIME;      // приращение времени с прошлого вызова (по модулю 2^32)
    tElapsed : TIME;    // прошло с фронта IN (с насыщением на T_MAX)
END_VAR
VAR CONSTANT
    T_MAX : TIME := T#49D17H2M47S295MS;  // максимум TIME (2^32 - 1 мс): насыщение «прошло»
END_VAR
