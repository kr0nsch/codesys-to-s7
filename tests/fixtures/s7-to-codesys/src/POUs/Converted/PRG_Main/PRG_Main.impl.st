// Initial_Call (вход OB S7): TRUE только в первом цикле после запуска — эмуляция s7conv
Initial_Call := NOT xS7convFirstCycleDone;
xS7convFirstCycleDone := TRUE;
IF Initial_Call THEN
    DB_Plant.plantMode := 1;
END_IF

// REGION Safety and analog inputs
DB_Plant.estopOk := GVL_IO.EStop_Ok;
GVL_InstanceDBs.DB_PT101(raw := GVL_IO.PT101_Raw);
GVL_InstanceDBs.DB_LT101(raw := GVL_IO.LT101_Raw);
DB_Plant.tankLevel := GVL_InstanceDBs.DB_LT101.value;
// MIGRATION-TODO: %IW272:P: прямой доступ к периферии (:P) не поддерживается (стр. 67)
// "DB_Plant".pressureFastRaw := %IW272:P;  // прямое чтение периферии мимо образа процесса
// END_REGION Safety and analog inputs

// REGION Alarms
GVL_InstanceDBs.DB_AlarmPT101(condition := GVL_InstanceDBs.DB_PT101.alarmHH OR GVL_InstanceDBs.DB_PT101.channelFault,
                              ack := DB_Hmi.alarmAck OR GVL_IO.Btn_Ack,
                              onDelay := T#5S);
GVL_IO.Lamp_Alarm := GVL_InstanceDBs.DB_AlarmPT101.alarm OR NOT DB_Plant.estopOk;
DB_Plant.alarmWord.0 := GVL_InstanceDBs.DB_AlarmPT101.active;
DB_Plant.alarmWord.1 := GVL_InstanceDBs.DB_P101.fault;
DB_Plant.alarmWord.2 := GVL_InstanceDBs.DB_P102.fault;
DB_Plant.alarmWord.3 := GVL_InstanceDBs.DB_P103.fault;
DB_Plant.alarmWord.4 := GVL_InstanceDBs.DB_Backwash.fault;
// END_REGION Alarms

// REGION Mode and pump group
GVL_InstanceDBs.DB_Mode(localSwitch := GVL_IO.Sw_Local, modeRequest := DB_Hmi.modeRequest, hmiCmd := DB_Hmi.cmdWord);
DB_Hmi.modeRequest := -1;

IF NOT DB_Plant.estopOk OR GVL_InstanceDBs.DB_Mode.mode <> 2 THEN
    demandPumps := 0;
ELSIF GVL_InstanceDBs.DB_PT101.value <= DB_Hmi.setpointPressure - 0.5 THEN
    demandPumps := 2;
ELSIF GVL_InstanceDBs.DB_PT101.value < DB_Hmi.setpointPressure THEN
    demandPumps := 1;
ELSIF GVL_InstanceDBs.DB_PT101.value > DB_Hmi.setpointPressure + 0.3 THEN
    demandPumps := 0;
ELSE
    demandPumps := GVL_InstanceDBs.DB_PumpAlt.runningCount;
END_IF

GVL_InstanceDBs.DB_PumpAlt(demand := demandPumps,
                           available1 := NOT GVL_InstanceDBs.DB_P101.fault AND GVL_IO.P101_ThermalOk,
                           available2 := NOT GVL_InstanceDBs.DB_P102.fault AND GVL_IO.P102_ThermalOk,
                           available3 := NOT GVL_InstanceDBs.DB_P103.fault AND GVL_IO.P103_ThermalOk,
                           alternate := FALSE);

GVL_InstanceDBs.DB_P101(autoMode := GVL_InstanceDBs.DB_Mode.mode = 2,
                        autoStart := GVL_InstanceDBs.DB_PumpAlt.run1,
                        manStart := DB_Hmi.pump[1].startReq,
                        manStop := DB_Hmi.pump[1].stopReq OR GVL_InstanceDBs.DB_Mode.mode = 0,
                        feedback := GVL_IO.P101_Fbk,
                        thermalOk := GVL_IO.P101_ThermalOk,
                        reset := DB_Hmi.pump[1].resetReq,
                        runCmd => GVL_IO.P101_Run);
GVL_InstanceDBs.DB_P102(autoMode := GVL_InstanceDBs.DB_Mode.mode = 2,
                        autoStart := GVL_InstanceDBs.DB_PumpAlt.run2,
                        manStart := DB_Hmi.pump[2].startReq,
                        manStop := DB_Hmi.pump[2].stopReq OR GVL_InstanceDBs.DB_Mode.mode = 0,
                        feedback := GVL_IO.P102_Fbk,
                        thermalOk := GVL_IO.P102_ThermalOk,
                        reset := DB_Hmi.pump[2].resetReq,
                        runCmd => GVL_IO.P102_Run);
GVL_InstanceDBs.DB_P103(autoMode := GVL_InstanceDBs.DB_Mode.mode = 2,
                        autoStart := GVL_InstanceDBs.DB_PumpAlt.run3,
                        manStart := DB_Hmi.pump[3].startReq,
                        manStop := DB_Hmi.pump[3].stopReq OR GVL_InstanceDBs.DB_Mode.mode = 0,
                        feedback := GVL_IO.P103_Fbk,
                        thermalOk := GVL_IO.P103_ThermalOk,
                        reset := DB_Hmi.pump[3].resetReq);
GVL_IO.P103_Run := GVL_InstanceDBs.DB_P103.runCmd;

DB_Plant.pumpStatus[1] := GVL_InstanceDBs.DB_P101.status;
DB_Plant.pumpStatus[2] := GVL_InstanceDBs.DB_P102.status;
DB_Plant.pumpStatus[3] := GVL_InstanceDBs.DB_P103.status;
// END_REGION Mode and pump group

// REGION Filter backwash
// MIGRATION-CHECK: S5Time → TIME: в S7 S5TIME — BCD с шагом 10 мс…10 с, диапазон до 2h46m30s (стр. 137)
GVL_InstanceDBs.DB_LS201(raw := GVL_IO.LS201_Drained, onDelayS5 := T#300MS);
GVL_InstanceDBs.DB_Backwash(start := DB_Hmi.backwashStart,
                            stop := DB_Hmi.backwashStop OR NOT DB_Plant.estopOk,
                            permissive := DB_Plant.tankLevel > 1.5,
                            levelLow := GVL_InstanceDBs.DB_LS201.debounced,
                            levelHigh := GVL_IO.LS202_Full,
                            reset := DB_Hmi.alarmAck);
GVL_IO.XV_Drain := GVL_InstanceDBs.DB_Backwash.drainValve;
GVL_IO.Q_AirBlower := GVL_InstanceDBs.DB_Backwash.airBlower;
GVL_IO.Q_WashPump := GVL_InstanceDBs.DB_Backwash.washPump;

GVL_InstanceDBs.DB_XV201(cmdOpen := GVL_InstanceDBs.DB_Backwash.inletValve,
                         cmdClose := NOT GVL_InstanceDBs.DB_Backwash.inletValve,
                         limitOpen := GVL_IO.XV201_Opened,
                         limitClosed := GVL_IO.XV201_Closed,
                         reset := DB_Hmi.alarmAck);
GVL_IO.XV201_Open := GVL_InstanceDBs.DB_XV201.coilOpen;
GVL_IO.XV201_Close := GVL_InstanceDBs.DB_XV201.coilClose;
// END_REGION Filter backwash

// REGION Dosing
GVL_InstanceDBs.DB_Dosing(pulseInput := GVL_IO.FQ201_Pulse, reset := DB_Hmi.resetTotal);
GVL_Markers.HMI_DosingPacked := GVL_InstanceDBs.DB_Dosing.packedCounters;
// END_REGION Dosing

// REGION Flow statistics once per second
shiftNow := GVL_Markers.Clock_1Hz AND NOT DB_Plant.clockMem;
DB_Plant.clockMem := GVL_Markers.Clock_1Hz;
DB_Plant.flowSampleCount := FC_Statistics(newSample := GVL_InstanceDBs.DB_FT101.value,
                                          shift := shiftNow,
                                          validLow := 0.0,
                                          validHigh := 1200.0,
                                          minValue => DB_Plant.flowMin,
                                          maxValue => DB_Plant.flowMax,
                                          average => DB_Plant.flowAvg,
                                          samples := DB_Plant.flowSamples);
// END_REGION Flow statistics once per second

// REGION Event log and legacy telegram
IF GVL_InstanceDBs.DB_AlarmPT101.active THEN
    eventCode := 101;
ELSIF GVL_InstanceDBs.DB_P101.fault THEN
    eventCode := 201;
ELSIF GVL_InstanceDBs.DB_P102.fault THEN
    eventCode := 202;
ELSIF GVL_InstanceDBs.DB_P103.fault THEN
    eventCode := 203;
ELSE
    eventCode := 0;
END_IF
// MIGRATION-TODO: параметр extraInfo не перенесён (Variant — нет аналога в CODESYS; переписать (ANY, POINTER или
//                 перегрузка)) — аргумент опущен (стр. 189)
GVL_InstanceDBs.DB_Logger(eventCode := eventCode, eventText := 'PLANT EVENT', clear := FALSE);

// MIGRATION-TODO: параметр source не перенесён (Any (указатель S7) — нет аналога) — аргумент опущен (стр. 194)
GVL_InstanceDBs.DB_LegacyTlg(send := shiftNow, statusWord := DB_Plant.alarmWord, archiveDb := 40);
// END_REGION Event log and legacy telegram

// REGION Legacy HMI memory words
GVL_Markers.HMI_StatusPT101 := GVL_InstanceDBs.DB_PT101.statusWord;
GVL_Markers.HMI_P101Running := GVL_InstanceDBs.DB_P101.status.running;
DB_Plant.heartbeat := INT_TO_BYTE(BYTE_TO_INT(DB_Plant.heartbeat) + 1);
// END_REGION Legacy HMI memory words
