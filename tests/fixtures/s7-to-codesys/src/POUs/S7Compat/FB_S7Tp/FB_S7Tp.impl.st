tNow := F_S7Now();
// фронт IN вне импульса: начало импульса
IF IN AND NOT xInPrev AND NOT Q THEN
    tStart := tNow;
    Q := TRUE;
END_IF

IF Q THEN
    tElapsed := tNow - tStart;
    IF tElapsed >= PT THEN
        Q := FALSE;
        ET := PT;
    ELSE
        ET := tElapsed;
    END_IF
END_IF

// импульса нет и IN = FALSE: ET сбрасывается (после импульса при IN = TRUE ET = PT)
IF NOT IN AND NOT Q THEN
    ET := T#0MS;
END_IF
xInPrev := IN;
