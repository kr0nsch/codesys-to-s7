// REGION Channel diagnostics
channelFault := raw > RAW_OVERSHOOT_MAX OR raw < RAW_UNDERSHOOT_MIN;
overrange := NOT channelFault AND raw > RAW_NOMINAL_HIGH;
underrange := NOT channelFault AND raw < RAW_NOMINAL_LOW;
// END_REGION Channel diagnostics

// REGION Scaling
IF simulation THEN
    value := simValue;
    valid := TRUE;
ELSIF channelFault THEN
    value := substitute;
    valid := FALSE;
ELSE
    rawClamped := LIMIT(RAW_NOMINAL_LOW, raw, RAW_NOMINAL_HIGH);
    normalized := F_NormX(rMin := RAW_NOMINAL_LOW, rValue := rawClamped, rMax := RAW_NOMINAL_HIGH);
    value := F_ScaleX(rMin := rangeLow, rValue := normalized, rMax := rangeHigh);
    valid := TRUE;
END_IF
// END_REGION Scaling

// REGION Limits with hysteresis
IF valid THEN
    IF value >= limitHH THEN
        alarmHH := TRUE;
    ELSIF value < limitHH - hysteresis THEN
        alarmHH := FALSE;
    END_IF

    IF value >= limitH THEN
        warnH := TRUE;
    ELSIF value < limitH - hysteresis THEN
        warnH := FALSE;
    END_IF

    IF value <= limitL THEN
        warnL := TRUE;
    ELSIF value > limitL + hysteresis THEN
        warnL := FALSE;
    END_IF

    IF value <= limitLL THEN
        alarmLL := TRUE;
    ELSIF value > limitLL + hysteresis THEN
        alarmLL := FALSE;
    END_IF
ELSE
    alarmHH := FALSE;
    warnH := FALSE;
    warnL := FALSE;
    alarmLL := FALSE;
END_IF
// END_REGION Limits with hysteresis

// REGION Status word
statusWord := 16#0000;
statusWord.0 := valid;
statusWord.1 := channelFault;
statusWord.2 := overrange;
statusWord.3 := underrange;
statusWord.4 := alarmHH;
statusWord.5 := warnH;
statusWord.6 := warnL;
statusWord.7 := alarmLL;
statusWord.8 := simulation;
// END_REGION Status word
