FUNCTION_BLOCK FB_Case
VAR
    a : INT;
    b : INT;
    i : INT;
    d : DINT;
    r : REAL;
    x : BOOL;
    y : BOOL;
    s : STRING(80);
    w : WORD;
    t : TIME;
END_VAR
i := MUX(a, 1, 2, 3);
END_FUNCTION_BLOCK
