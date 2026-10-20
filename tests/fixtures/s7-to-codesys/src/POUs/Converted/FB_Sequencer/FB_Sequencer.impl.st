// REGION Edges and step time
edgeStart(CLK := start);
edgeReset(CLK := reset);
stepAtEntry := stepNo;
stepRunning := stepNo >= STEP_DRAIN AND stepNo <= STEP_REFILL;
tonStep(IN := stepRunning, PT := STEP_TIMER_MAX);
// END_REGION Edges and step time

// REGION Step transitions
IF stop AND stepRunning THEN
    stepNo := STEP_IDLE;
ELSE
    CASE stepNo OF
        0:
            // IDLE
            IF edgeStart.Q AND permissive AND NOT stop THEN
                stepNo := STEP_DRAIN;
            END_IF
        10:
            // DRAIN
            IF levelLow THEN
                stepNo := STEP_AIR_SCOUR;
            ELSIF tonStep.ET >= drainTimeout THEN
                faultStep := STEP_DRAIN;
                stepNo := STEP_FAULT;
            END_IF
        20:
            // AIR SCOUR
            IF tonStep.ET >= airTime THEN
                stepNo := STEP_BACKWASH;
            END_IF
        30:
            // BACKWASH
            IF tonStep.ET >= washTime THEN
                stepNo := STEP_REFILL;
            END_IF
        40:
            // REFILL
            IF levelHigh THEN
                cycleCount := cycleCount + 1;
                stepNo := STEP_IDLE;
            ELSIF tonStep.ET >= refillTimeout THEN
                faultStep := STEP_REFILL;
                stepNo := STEP_FAULT;
            END_IF
        90:
            // FAULT
            IF edgeReset.Q THEN
                faultStep := 0;
                stepNo := STEP_IDLE;
            END_IF
    ELSE
        stepNo := STEP_IDLE;
    END_CASE
END_IF
// END_REGION Step transitions

// REGION Restart step timer on transition
IF stepNo <> stepAtEntry THEN
    tonStep(IN := FALSE, PT := STEP_TIMER_MAX);
    tonStep(IN := stepNo >= STEP_DRAIN AND stepNo <= STEP_REFILL, PT := STEP_TIMER_MAX);
END_IF
// END_REGION Restart step timer on transition

// REGION Outputs
drainValve := stepNo = STEP_DRAIN OR stepNo = STEP_BACKWASH;
airBlower := stepNo = STEP_AIR_SCOUR;
washPump := stepNo = STEP_BACKWASH;
inletValve := stepNo = STEP_REFILL;
busy := stepNo >= STEP_DRAIN AND stepNo <= STEP_REFILL;
fault := stepNo = STEP_FAULT;

CASE stepNo OF
    0:
        stepText := 'IDLE';
    10:
        stepText := 'DRAIN';
    20:
        stepText := 'AIR SCOUR';
    30:
        stepText := 'BACKWASH';
    40:
        stepText := 'REFILL';
    90:
        stepText := 'FAULT';
END_CASE
// END_REGION Outputs
