// REGION Limit switches
debOpen(raw := limitOpen);
debClosed(raw := limitClosed);
isOpen := debOpen.debounced;
isClosed := debClosed.debounced;
// END_REGION Limit switches

// REGION Reset and discrepancy
edgeReset(CLK := reset);
IF edgeReset.Q AND NOT (isOpen AND isClosed) THEN
    state := 0;
    faultCode := 0;
END_IF
IF isOpen AND isClosed THEN
    state := 9;
    faultCode := 2;
END_IF
// END_REGION Reset and discrepancy

// REGION State machine
tonOpening(IN := state = 2, PT := travelTime);
tonClosing(IN := state = 4, PT := travelTime);
lostOpen(CLK := isOpen);
lostClosed(CLK := isClosed);

CASE state OF
    0:
        IF cmdClose THEN
            state := 4;
        ELSIF cmdOpen THEN
            state := 2;
        ELSIF isClosed THEN
            state := 1;
        ELSIF isOpen THEN
            state := 3;
        END_IF
    1:
        IF cmdOpen AND NOT cmdClose THEN
            state := 2;
        ELSIF lostClosed.Q THEN
            state := 9;
            faultCode := 3;
        END_IF
    2:
        IF cmdClose THEN
            state := 4;
        ELSIF isOpen THEN
            state := 3;
        ELSIF tonOpening.Q THEN
            state := 9;
            faultCode := 1;
        END_IF
    3:
        IF cmdClose THEN
            state := 4;
        ELSIF lostOpen.Q THEN
            state := 9;
            faultCode := 3;
        END_IF
    4:
        IF isClosed THEN
            state := 1;
        ELSIF cmdOpen AND NOT cmdClose THEN
            state := 2;
        ELSIF tonClosing.Q THEN
            state := 9;
            faultCode := 1;
        END_IF
    9:
        ;  // ожидание сброса
ELSE
    state := 0;
END_CASE
// END_REGION State machine

// REGION Outputs
coilOpen := state = 2;
coilClose := state = 4;
tpOpen(IN := state = 2, PT := pulseTime);
tpClose(IN := state = 4, PT := pulseTime);
pulseOpen := tpOpen.Q;
pulseClose := tpClose.Q;
// END_REGION Outputs
