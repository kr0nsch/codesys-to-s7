statusCopy := statusWord;
done := FALSE;

IF NOT (send AND NOT sendMem) THEN
    sendMem := send;
    // MIGRATION-TODO: GOTO — переходы не переносятся (переписать структурно) (стр. 87)
    // GOTO lblExit;
END_IF
sendMem := send;

// MIGRATION-TODO: использует «srcPtr», объявление которой не перенесено (Any (указатель S7) — нет аналога) (стр.
//                 91)
// #srcPtr := #source;
// MIGRATION-TODO: использует «srcView», объявление которой не перенесено (AT (наложение переменных S7)) (стр. 92)
// IF #srcView.length > 16 THEN
//     #error := TRUE;
//     ENO := FALSE;
//     GOTO lblExit;
// END_IF;

// MIGRATION-TODO: BLKMOV: нет прямого аналога в CODESYS Standard (стр. 98)
// #retVal := BLKMOV(SRCBLK := #source, DSTBLK => P#DB30.DBX4.0 BYTE 16);
// MIGRATION-TODO: адрес %DB30.DBW0 не поддерживается (только %I, %Q, %M) (стр. 99)
// %DB30.DBW0 := #statusCopy;
seqNo := seqNo + 1;
// MIGRATION-TODO: адрес %DB30.DBW2 не поддерживается (только %I, %Q, %M) (стр. 101)
// %DB30.DBW2 := INT_TO_WORD(#seqNo);

// MIGRATION-TODO: использует «statusBits», объявление которой не перенесено (AT (наложение переменных S7)) (стр.
//                 103)
// IF #statusBits[3] THEN
//     WORD_TO_BLOCK_DB(INT_TO_WORD(#archiveDb)).DW[0] := #statusCopy;
// END_IF;

IF retVal <> 0 THEN
    error := TRUE;
    // MIGRATION-TODO: ENO: флаги EN/ENO/OK S7 не поддерживаются (стр. 109)
    // ENO := FALSE;
    // MIGRATION-TODO: GOTO — переходы не переносятся (переписать структурно) (стр. 110)
    // GOTO lblRetry;
END_IF
done := TRUE;
error := FALSE;
retries := 0;

// MIGRATION-TODO: метка перехода — переходы не переносятся (стр. 116)
// lblRetry:
// MIGRATION-TODO: S_ODT: нет прямого аналога в CODESYS Standard (стр. 117)
// #remaining := S_ODT(T_NO := "T_Retry",
//                     S := #error,
//                     TV := #retryDelay,
//                     R := #done,
//                     Q => #retryElapsed,
//                     BI => #timerValue);
IF retryElapsed AND retries < 3 THEN
    retries := retries + 1;
    sendMem := FALSE;
END_IF

// MIGRATION-TODO: метка перехода — переходы не переносятся (стр. 128)
// lblExit:
;
