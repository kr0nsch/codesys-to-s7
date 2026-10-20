// REGION Fault reset
edgeReset(CLK := reset);
IF edgeReset.Q AND thermalOk THEN
    fault := FALSE;
    faultCode := FAULT_NONE;
END_IF
// END_REGION Fault reset

// REGION Thermal protection
IF NOT thermalOk AND NOT fault THEN
    fault := TRUE;
    faultCode := FAULT_THERMAL;
END_IF
// END_REGION Thermal protection

// REGION Mode and demand
IF autoMode THEN
    manRun := autoStart;  // слежение за командой авто
ELSIF manStop OR fault THEN
    manRun := FALSE;
ELSIF manStart THEN
    manRun := TRUE;
END_IF

IF autoMode THEN
    demand := autoStart;
ELSE
    demand := manRun;
END_IF
runCmd := demand AND NOT fault;
// END_REGION Mode and demand

// REGION Feedback monitoring
IF NOT runCmd THEN
    feedbackSeen := FALSE;
ELSIF feedback THEN
    feedbackSeen := TRUE;
END_IF

tonFeedback(IN := runCmd XOR feedback, PT := feedbackTime);

IF tonFeedback.Q AND NOT fault THEN
    fault := TRUE;
    IF NOT runCmd THEN
        faultCode := FAULT_UNEXPECTED_FEEDBACK;
    ELSIF feedbackSeen THEN
        faultCode := FAULT_FEEDBACK_LOST;
    ELSE
        faultCode := FAULT_NO_FEEDBACK;
    END_IF
    runCmd := FALSE;
END_IF
// END_REGION Feedback monitoring

// REGION Statistics and HMI status
edgeRun(CLK := runCmd);
IF edgeRun.Q THEN
    startCount := startCount + 1;
END_IF

status.running := runCmd AND feedback;
status.fault := fault;
status.autoMode := autoMode;
status.faultCode := faultCode;
status.startCount := startCount;
// END_REGION Statistics and HMI status
