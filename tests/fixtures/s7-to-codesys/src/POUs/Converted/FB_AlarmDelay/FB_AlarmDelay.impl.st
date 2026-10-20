edgeAck(CLK := ack);

// REGION Delays
tonOn(IN := condition AND enable, PT := onDelay);
tofOff(IN := tonOn.Q, PT := offDelay);
active := tofOff.Q AND enable;
// END_REGION Delays

// REGION Acknowledge
IF edgeAck.Q THEN
    unacked := FALSE;
END_IF

edgeActive(CLK := active);
IF edgeActive.Q THEN
    unacked := TRUE;
    count := count + 1;
END_IF

IF NOT enable THEN
    unacked := FALSE;
END_IF
// END_REGION Acknowledge

// REGION Outputs
alarm := active OR unacked;

IF active AND unacked THEN
    state := STATE_ACTIVE_UNACKED;
ELSIF active THEN
    state := STATE_ACTIVE_ACKED;
ELSIF unacked THEN
    state := STATE_CLEARED_UNACKED;
ELSE
    state := STATE_NORMAL;
END_IF
// END_REGION Outputs
