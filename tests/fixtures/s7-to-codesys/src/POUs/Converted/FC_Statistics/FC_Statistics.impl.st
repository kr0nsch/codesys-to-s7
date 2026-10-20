minValue := 0.0;
maxValue := 0.0;
average := 0.0;

IF validLow > validHigh THEN
    FC_Statistics := -1;
    RETURN;
END_IF

// REGION Shift window
IF shift THEN
    FOR i := 1 TO SAMPLE_COUNT - 1 BY 1 DO
        samples[i] := samples[i + 1];
    END_FOR
    samples[SAMPLE_COUNT] := newSample;
END_IF
// END_REGION Shift window

// REGION Statistics
count := 0;
sum := 0.0;
FOR i := 1 TO SAMPLE_COUNT DO
    IF samples[i] < validLow OR samples[i] > validHigh THEN
        CONTINUE;
    END_IF
    IF count = 0 THEN
        minValue := samples[i];
        maxValue := samples[i];
    ELSE
        minValue := MIN(minValue, samples[i]);
        maxValue := MAX(maxValue, samples[i]);
    END_IF
    count := count + 1;
    sum := sum + REAL_TO_LREAL(samples[i]);
END_FOR

IF count > 0 THEN
    average := LREAL_TO_REAL(sum / INT_TO_LREAL(count));
END_IF
// END_REGION Statistics

FC_Statistics := count;
