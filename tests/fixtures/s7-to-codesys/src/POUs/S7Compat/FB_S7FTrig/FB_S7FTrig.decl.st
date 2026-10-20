// Назначение: детектор спада с интерфейсом F_TRIG (CLK, Q) и семантикой S7 для кода, сконвертированного
//             s7conv с --f-trig s7compat: Q = NOT CLK И CLK прошлого вызова; до первого вызова прошлое
//             значение CLK — FALSE, поэтому на первом вызове с CLK = FALSE спада нет (так ведёт себя
//             F_TRIG S7). В CODESYS 3.5.17.30 (Standard 3.5.17.0) F_TRIG Standard ведёт себя так же — тест
//             StandardFTrigMatchesS7 и строка 1 сценария FB_PumpAlternation/RotateOnStop (docs/TEST_REPORT.md);
//             блок нужен для версии Standard, где этот тест упадёт, и как эталон семантики S7 в тестах.
// Автор:      kr0nsch
// Версия:     0.1.1
// Документ:   docs/MAPPING.md, раздел «Функциональные блоки инструкций»
FUNCTION_BLOCK FB_S7FTrig
VAR_INPUT
    CLK : BOOL;         // lint:allow STL007 интерфейс F_TRIG: имя входа как у Standard.F_TRIG
END_VAR
VAR_OUTPUT
    Q : BOOL;           // lint:allow STL007 интерфейс F_TRIG: спад обнаружен
END_VAR
VAR
    xClkPrev : BOOL;    // CLK прошлого вызова; FALSE до первого вызова — как память фронта S7
END_VAR
