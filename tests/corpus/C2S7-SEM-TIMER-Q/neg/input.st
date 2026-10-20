FUNCTION_BLOCK FB_Case
VAR
    tDelay : TON;
    x : BOOL;
    y : BOOL;
END_VAR
tDelay(IN := x, PT := T#1S);
y := tDelay.Q;
END_FUNCTION_BLOCK
