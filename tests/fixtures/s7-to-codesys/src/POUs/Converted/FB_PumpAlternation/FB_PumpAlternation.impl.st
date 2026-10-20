// REGION Inputs
avail[1] := available1;
avail[2] := available2;
avail[3] := available3;
required := LIMIT(0, demand, PUMP_COUNT);
// END_REGION Inputs

// REGION Lead rotation
edgeAlternate(CLK := alternate);
edgeStop(CLK := required > 0);
rotate := edgeAlternate.Q OR edgeStop.Q AND rotateOnStop;

IF lead < 1 OR lead > PUMP_COUNT THEN
    lead := 1;
END_IF

IF rotate THEN
    candidate := lead;
    tries := 0;
    REPEAT
        candidate := candidate MOD PUMP_COUNT + 1;
        tries := tries + 1;
    UNTIL avail[candidate] OR tries >= PUMP_COUNT
    END_REPEAT
    IF avail[candidate] THEN
        lead := candidate;
    END_IF
END_IF
// END_REGION Lead rotation

// REGION Assignment
assigned := 0;
FOR k := 0 TO PUMP_COUNT - 1 DO
    idx := (lead - 1 + k) MOD PUMP_COUNT + 1;
    runReq[idx] := avail[idx] AND assigned < required;
    IF runReq[idx] THEN
        assigned := assigned + 1;
    END_IF
END_FOR
// END_REGION Assignment

// REGION Outputs
run1 := runReq[1];
run2 := runReq[2];
run3 := runReq[3];
leadPump := lead;
runningCount := assigned;
shortage := assigned < required;
// END_REGION Outputs
