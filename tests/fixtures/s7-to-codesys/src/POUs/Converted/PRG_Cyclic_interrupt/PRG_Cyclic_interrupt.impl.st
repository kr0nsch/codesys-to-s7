// Initial_Call (вход OB S7): TRUE только в первом цикле после запуска — эмуляция s7conv
Initial_Call := NOT xS7convFirstCycleDone;
xS7convFirstCycleDone := TRUE;
// REGION Flow and totalizer
GVL_InstanceDBs.DB_FT101(raw := GVL_IO.FT101_Raw);
GVL_InstanceDBs.DB_FQ101(flow := GVL_InstanceDBs.DB_FT101.value,
                         cycleTime := CYCLE_TIME,
                         enable := GVL_InstanceDBs.DB_FT101.valid,
                         reset := DB_Hmi.resetTotal);
DB_Plant.totalVolume := GVL_InstanceDBs.DB_FQ101.lifetimeTotal;
DB_Plant.shiftData.volume := GVL_InstanceDBs.DB_FQ101.total;
// END_REGION Flow and totalizer

// REGION Pressure control
GVL_InstanceDBs.DB_RampSP(target := DB_Hmi.setpointPressure, cycleTime := CYCLE_TIME);
GVL_InstanceDBs.DB_PIC101(sp := GVL_InstanceDBs.DB_RampSP.rampValue,
                          pv := GVL_InstanceDBs.DB_PT101.value,
                          manual := DB_Hmi.pidManual OR NOT GVL_InstanceDBs.DB_PT101.valid,
                          manValue := DB_Hmi.pidManualValue,
                          cycleTime := CYCLE_TIME);
speedNorm := F_NormX(rMin := 0.0, rValue := GVL_InstanceDBs.DB_PIC101.outPercent, rMax := 100.0);
// MIGRATION-CHECK: SCALE_X с целым OUT: REAL_TO_INT округляет — сверить с S7 (стр. 67)
GVL_IO.VFD_SpeedRef := REAL_TO_INT(F_ScaleX(rMin := 0, rValue := speedNorm, rMax := 27648));
// END_REGION Pressure control
