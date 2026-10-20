tNow := F_S7Now();
IF IN THEN
    Q := TRUE;
    ET := T#0MS;
    xRunning := FALSE;
ELSIF xInPrev THEN
    // спад IN: начало отсчёта задержки выключения
    tStart := tNow;
    xRunning := TRUE;
END_IF

IF xRunning THEN
    tElapsed := tNow - tStart;
    IF tElapsed >= PT THEN
        Q := FALSE;
        ET := PT;
        xRunning := FALSE;
    ELSE
        ET := tElapsed;
    END_IF
END_IF
xInPrev := IN;
