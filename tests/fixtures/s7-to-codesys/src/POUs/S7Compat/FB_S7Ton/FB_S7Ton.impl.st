tNow := F_S7Now();
// приращение с прошлого вызова: присваивание TIME даёт разность по модулю 2^32 — верно и при переходе
// TIME через ноль (промежуточный результат выражения может вычисляться шире 32 бит)
tDelta := tNow - tLast;
IF NOT IN OR NOT xInPrev THEN
    // IN = FALSE или фронт IN (первый вызов с IN = TRUE): отсчёт с нуля
    tElapsed := T#0MS;
ELSIF tElapsed > T_MAX - tDelta THEN
    // насыщение вместо переполнения: IN = TRUE дольше 2^32 мс
    tElapsed := T_MAX;
ELSE
    tElapsed := tElapsed + tDelta;
END_IF
Q := IN AND tElapsed >= PT;
ET := MIN(tElapsed, PT);
tLast := tNow;
xInPrev := IN;
