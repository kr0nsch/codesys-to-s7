// REGION Pulses
edgePulse(CLK := pulseInput);
doseDone := FALSE;
IF reset THEN
    pulseCounter := 0;
ELSIF edgePulse.Q THEN
    pulseCounter := pulseCounter + 1;
    IF pulsesPerDose > 0 AND pulseCounter >= pulsesPerDose THEN
        doseDone := TRUE;
        pulseCounter := 0;
    END_IF
END_IF
// END_REGION Pulses

// REGION Batch counter
ctuBatch(CU := doseDone, RESET := reset, PV := INT_TO_WORD(batchPreset));
doseCount := WORD_TO_INT(ctuBatch.CV);
batchDone := ctuBatch.Q;
// END_REGION Batch counter

// REGION Status and packing
statusByte := 16#00;
statusByte.0 := batchDone;
statusByte.1 := pulseCounter > 0;
statusByte.2 := pulsesPerDose <= 0;

packedCounters := SHL(WORD_TO_DWORD(INT_TO_WORD(doseCount)), 16) OR WORD_TO_DWORD(INT_TO_WORD(pulseCounter));
// MIGRATION-CHECK: срез .%W0 → DWORD_TO_WORD(SHR(...)): нумерация срезов S7 от младшей части — сверить с источником
//                  (стр. 90)
lowWordCopy := DWORD_TO_WORD(packedCounters);
// MIGRATION-CHECK: срез .%B1 → WORD_TO_BYTE(SHR(...)): нумерация срезов S7 от младшей части — сверить с источником
//                  (стр. 91)
highByteOfLow := WORD_TO_BYTE(SHR(lowWordCopy, 8));
// END_REGION Status and packing
