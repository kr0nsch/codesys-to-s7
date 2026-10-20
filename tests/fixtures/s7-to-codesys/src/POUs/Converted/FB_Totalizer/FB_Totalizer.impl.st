// REGION Increment
cutoffActive := flow < lowFlowCutoff;
dtSeconds := DINT_TO_LREAL(TIME_TO_DINT(cycleTime)) / MS_PER_SECOND;
IF enable AND NOT cutoffActive THEN
    deltaVolume := REAL_TO_LREAL(flow) * dtSeconds / SECONDS_PER_HOUR;
ELSE
    deltaVolume := 0.0;
END_IF
// END_REGION Increment

// REGION Lifetime total
lifetimeAcc := lifetimeAcc + deltaVolume;
lifetimeTotal := lifetimeAcc;
// END_REGION Lifetime total

// REGION Resettable total and pulses
pulse := FALSE;
IF reset THEN
    total := 0.0;
    pulseCount := 0;
    pulseAcc := 0.0;
ELSE
    total := total + deltaVolume;
    pulseAcc := pulseAcc + deltaVolume;
    IF pulseVolume > 0.0 AND pulseAcc >= REAL_TO_LREAL(pulseVolume) THEN
        pulse := TRUE;
        pulseCount := pulseCount + 1;
        pulseAcc := pulseAcc - REAL_TO_LREAL(pulseVolume);
    END_IF
END_IF
// END_REGION Resettable total and pulses
