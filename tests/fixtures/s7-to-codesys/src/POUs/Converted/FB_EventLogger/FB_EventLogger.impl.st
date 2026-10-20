// MIGRATION-TODO: RUNTIME: нет прямого аналога в CODESYS Standard (стр. 81)
// #execTime := RUNTIME(#runtimeMem);

// REGION Clear
IF clear THEN
    FOR i := 0 TO BUFFER_SIZE - 1 DO
        buffer[i].code := 0;
        buffer[i].aux := 0;
        buffer[i].text := '';
    END_FOR
    writeIndex := 0;
END_IF
// END_REGION Clear

// REGION New event
IF eventCode <> 0 AND eventCode <> lastCode THEN
    // MIGRATION-TODO: RD_SYS_T: нет прямого аналога в CODESYS Standard (стр. 96)
    // #ret := RD_SYS_T(OUT => #nowDt);
    error := ret_ <> 0;
    msg := CONCAT('E:', LEFT(eventText, 18));
    extraInt := 0;
    // MIGRATION-TODO: TypeOf: нет прямого аналога в CODESYS Standard (стр. 100)
    // IF TypeOf(#extraInfo) = Int THEN
    //     VariantGet(SRC := #extraInfo,
    //                DST => #extraInt);
    // END_IF;
    buffer[writeIndex].stamp := nowDt;
    buffer[writeIndex].code := eventCode;
    buffer[writeIndex].aux := extraInt;
    buffer[writeIndex].text := msg;
    lastStamp := nowDt;
    writeIndex := (writeIndex + 1) MOD BUFFER_SIZE;
END_IF
lastCode := eventCode;
// END_REGION New event

// REGION Count entries
i := 0;
WHILE i < BUFFER_SIZE DO
    IF buffer[i].code = 0 THEN
        EXIT;
    END_IF
    i := i + 1;
END_WHILE
entries := i;
// END_REGION Count entries

// REGION Legacy telegram DB
// MIGRATION-TODO: PEEK: нет прямого аналога в CODESYS Standard (стр. 126)
// #telegramStatus := PEEK(area := #AREA_DB, dbNumber := #TELEGRAM_DB, byteOffset := 0);
heartbeat := INT_TO_BYTE(BYTE_TO_INT(heartbeat) + 1);
// MIGRATION-TODO: POKE: нет прямого аналога в CODESYS Standard (стр. 128)
// POKE(area := #AREA_DB,
//      dbNumber := #TELEGRAM_DB,
//      byteOffset := 35,
//      value := #heartbeat);
// END_REGION Legacy telegram DB
