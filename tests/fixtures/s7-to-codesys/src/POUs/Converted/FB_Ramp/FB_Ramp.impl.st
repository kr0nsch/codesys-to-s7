dtSeconds := DINT_TO_REAL(TIME_TO_DINT(cycleTime)) / 1000.0;
stepUp := MAX(rateUp, 0.0) * dtSeconds;
stepDown := MAX(rateDown, 0.0) * dtSeconds;
moving := FALSE;

IF NOT initDone THEN
    rampValue := target;
    initDone := TRUE;
ELSIF track THEN
    rampValue := trackValue;
ELSIF hold THEN
    ;
ELSIF rampValue < target THEN
    rampValue := MIN(rampValue + stepUp, target);
    moving := TRUE;
ELSIF rampValue > target THEN
    rampValue := MAX(rampValue - stepDown, target);
    moving := TRUE;
END_IF

atTarget := rampValue = target;
rising := moving AND rampValue < target;
falling := moving AND rampValue > target;
