signal := raw XOR invert;
// MIGRATION-CHECK: S5TI_TIM: S5Time уже сопоставлен с TIME — преобразование убрано (стр. 64)
onDelay := onDelayS5;
// MIGRATION-CHECK: S5TI_TIM: S5Time уже сопоставлен с TIME — преобразование убрано (стр. 65)
offDelay := offDelayS5;

tonOn(IN := signal, PT := onDelay);
tofOff(IN := tonOn.Q, PT := offDelay);
debounced := tofOff.Q;

edgeUp(CLK := debounced);
edgeDown(CLK := debounced);
rising := edgeUp.Q;
falling := edgeDown.Q;
IF rising OR falling THEN
    changeCount := changeCount + 1;
END_IF
