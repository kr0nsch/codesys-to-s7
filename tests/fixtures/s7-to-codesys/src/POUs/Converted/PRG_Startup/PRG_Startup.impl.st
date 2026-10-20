IF NOT xS7convStartupDone THEN
    xS7convStartupDone := TRUE;
    DB_Plant.plantMode := 0;
    DB_Hmi.cmdWord := 16#0000;
    DB_Hmi.modeRequest := -1;

    IF LostRetentive THEN
        DB_Plant.totalVolume := 0.0;
        DB_Plant.backwashCount := 0;
        FOR i := 1 TO 4 DO
            DB_Plant.filterRuntime[i] := T#0MS;
        END_FOR
    END_IF

    IF LostRTC THEN
        DB_Plant.clockLost := TRUE;
        // MIGRATION-TODO: WR_SYS_T: нет прямого аналога в CODESYS Standard (стр. 62)
        // #ret := WR_SYS_T("DB_Plant".defaultClock);
    END_IF
END_IF
