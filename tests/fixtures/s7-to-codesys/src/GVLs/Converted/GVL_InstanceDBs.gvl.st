// Назначение: экземпляры функциональных блоков и типизированные DB S7 (экземплярные DB → переменные GVL)
// Автор:      s7conv 0.1.0 (сгенерировано)
// Версия:     не указана
// Документ:   docs/MAPPING.md, раздел «DB»
{attribute 'qualified_only'}
VAR_GLOBAL
    DB_AlarmPT101 : FB_AlarmDelay; // samples/scl/DB_Plant.scl:236
    DB_Backwash : FB_Sequencer := (drainTimeout := T#90S); // samples/scl/DB_Plant.scl:200
    DB_Dosing : FB_BatchCounter := (pulsesPerDose := 50); // samples/scl/DB_Plant.scl:257
    DB_FQ101 : FB_Totalizer := (lowFlowCutoff := 2.0); // samples/scl/DB_Plant.scl:190
    DB_FT101 : FB_AnalogIn := (rangeHigh := 1200.0,
                               limitHH := 1150.0,
                               limitH := 1100.0,
                               limitL := 0.0,
                               limitLL := -1.0,
                               hysteresis := 10.0); // samples/scl/DB_Plant.scl:226
    DB_Logger : FB_EventLogger; // samples/scl/DB_Plant.scl:262
    DB_LS201 : FB_Debounce; // samples/scl/DB_Plant.scl:248
    DB_LT101 : FB_AnalogIn := (rangeHigh := 5.0,
                               limitHH := 4.8,
                               limitH := 4.5,
                               limitL := 1.0,
                               limitLL := 0.5,
                               hysteresis := 0.05); // samples/scl/DB_Plant.scl:216
    DB_Mode : FB_ModeSelect; // samples/scl/DB_Plant.scl:240
    DB_P101 : FB_Motor := (feedbackTime := T#5S); // samples/scl/DB_Plant.scl:146
    DB_P102 : FB_Motor := (feedbackTime := T#5S); // samples/scl/DB_Plant.scl:157
    DB_P103 : FB_Motor; // samples/scl/DB_Plant.scl:168
    DB_PIC101 : FB_PIController := (kp := 2.0, ti := T#20S); // samples/scl/DB_Plant.scl:178
    DB_PT101 : FB_AnalogIn := (rangeHigh := 16.0); // samples/scl/DB_Plant.scl:211
    DB_PumpAlt : FB_PumpAlternation; // samples/scl/DB_Plant.scl:244
    DB_RampSP : FB_Ramp; // samples/scl/DB_Plant.scl:270
    DB_RecipeActive : UDT_DosingRecipe := (name := 'SUMMER',
                                           doseStep := [0.8, 1.2, 1.5, 2.0]); // samples/scl/DB_Plant.scl:133
    DB_XV201 : FB_Valve := (travelTime := T#45S); // samples/scl/DB_Plant.scl:252
END_VAR
VAR_GLOBAL RETAIN
    // MIGRATION-CHECK: стандартный (неоптимизированный) экземплярный или типизированный DB без NON_RETAIN: в S7 он
    //                  реманентный целиком — объявлен в VAR_GLOBAL RETAIN GVL_InstanceDBs (стр. 266)
    DB_LegacyTlg : FB_LegacyTelegram; // samples/scl/DB_Plant.scl:266
END_VAR
