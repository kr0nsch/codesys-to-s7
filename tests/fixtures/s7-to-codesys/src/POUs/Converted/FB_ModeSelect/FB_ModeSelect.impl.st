// REGION Local switch
IF localSwitch THEN
    mode := 3;
    wasLocal := TRUE;
    hmiCmd := hmiCmd AND 16#FFF0;
ELSIF wasLocal THEN
    mode := 1;
    wasLocal := FALSE;
END_IF
// END_REGION Local switch

// REGION HMI request bits
IF NOT localSwitch THEN
    IF hmiCmd.2 THEN
        mode := 0;
    ELSIF hmiCmd.3 AND mode = 0 THEN
        mode := 1;
    ELSIF hmiCmd.1 AND mode <> 0 THEN
        mode := 1;
    ELSIF hmiCmd.0 AND mode <> 0 THEN
        mode := 2;
    END_IF
    hmiCmd := hmiCmd AND 16#FFF0;

    CASE modeRequest OF
        0:
            mode := 0;
        1, 2:
            IF mode <> 0 THEN
                mode := modeRequest;
            END_IF
        3..99:
            rejectCount := rejectCount + 1;
    END_CASE
END_IF
// END_REGION HMI request bits

// REGION Status
statusWord := 16#0000;
statusWord.0 := mode = 0;
statusWord.1 := mode = 1;
statusWord.2 := mode = 2;
statusWord.3 := mode = 3;
statusWord.8 := localSwitch;
// MIGRATION-CHECK: срез .%B1 → WORD_TO_BYTE(SHR(...)): нумерация срезов S7 от младшей части — сверить с источником
//                  (стр. 106)
statusHigh := WORD_TO_BYTE(SHR(statusWord, 8));

CASE mode OF
    0:
        modeText := 'OOS';
    1:
        modeText := 'MANUAL';
    2:
        modeText := 'AUTO';
    3:
        modeText := 'LOCAL';
END_CASE
// END_REGION Status
