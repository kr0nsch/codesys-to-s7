// REGION Error
IF reverseActing THEN
    e := sp - pv;
ELSE
    e := pv - sp;
END_IF
IF ABS(e) < deadband THEN
    e := 0.0;
END_IF
errorOut := e;
// END_REGION Error

// REGION Time base
dtSeconds := DINT_TO_LREAL(TIME_TO_DINT(cycleTime)) / MS_PER_SECOND;
tiSeconds := DINT_TO_LREAL(TIME_TO_DINT(ti)) / MS_PER_SECOND;
pPart := REAL_TO_LREAL(kp) * REAL_TO_LREAL(e);
// END_REGION Time base

// REGION Manual and automatic
IF manual THEN
    outPercent := LIMIT(outMin, manValue, outMax);
    integral := REAL_TO_LREAL(outPercent) - pPart;
ELSE
    IF tiSeconds > 0.0 THEN
        integral := integral + pPart * dtSeconds / tiSeconds;
    ELSE
        integral := 0.0;
    END_IF
    // Антинасыщение: P + I в пределах outMin...outMax
    upper := REAL_TO_LREAL(outMax) - pPart;
    lower := REAL_TO_LREAL(outMin) - pPart;
    integral := MIN(MAX(integral, lower), upper);
    outPercent := LIMIT(outMin, LREAL_TO_REAL(pPart + integral), outMax);
END_IF
// END_REGION Manual and automatic

// REGION Limits
atHighLimit := outPercent >= outMax;
atLowLimit := outPercent <= outMin;
// END_REGION Limits
