"""FB_Latch — фиксация команд пульта фильтра (ST, FUNCTION_BLOCK).

Поведение (модель scenarios/reference/model_FB_Latch.py):
- xSr — SR(SET1 := xSet, RESET := xReset): установка доминирует, при SET = RESET = 1 → TRUE;
- xRs — RS(SET := xSet, RESET1 := xReset): сброс доминирует, при SET = RESET = 1 → FALSE
  (одноимённые блоки S7 — наоборот: C2S7-SEM-SRRS, CDS_SR/CDS_RS);
- CTU(CU := xCu, RESET := xReset, PV := 3): wCu — счёт фронтов, xCuQ — wCu ≥ 3; RESET обнуляет;
- CTD(CD := xCd, LOAD := xLoad, PV := 2): LOAD ставит 2, фронт CD уменьшает до 0 и не ниже, xCdQ — wCd = 0
  (WORD без знака: стоит на нуле; проба M0);
- xRise/xFall — R_TRIG/F_TRIG по xClk; F_TRIG на первом вызове с CLK = FALSE спада не даёт (M0).
"""

from builder import Pou, St, V

POU = Pou(
    "FB_Latch",
    "functionBlock",
    St(
        "fbSr(SET1 := xSet, RESET := xReset, Q1 => xSr);\n"
        "fbRs(SET := xSet, RESET1 := xReset, Q1 => xRs);\n"
        "fbCtu(CU := xCu, RESET := xReset, PV := 3, Q => xCuQ, CV => wCu);\n"
        "fbCtd(CD := xCd, LOAD := xLoad, PV := 2, Q => xCdQ, CV => wCd);\n"
        "fbRise(CLK := xClk, Q => xRise);\n"
        "fbFall(CLK := xClk, Q => xFall);\n"
    ),
    [
        V("xSet", "BOOL", "VAR_INPUT"),
        V("xReset", "BOOL", "VAR_INPUT"),
        V("xCu", "BOOL", "VAR_INPUT"),
        V("xCd", "BOOL", "VAR_INPUT"),
        V("xLoad", "BOOL", "VAR_INPUT"),
        V("xClk", "BOOL", "VAR_INPUT"),
        V("xSr", "BOOL", "VAR_OUTPUT"),
        V("xRs", "BOOL", "VAR_OUTPUT"),
        V("xCuQ", "BOOL", "VAR_OUTPUT"),
        V("xCdQ", "BOOL", "VAR_OUTPUT"),
        V("wCu", "WORD", "VAR_OUTPUT"),
        V("wCd", "WORD", "VAR_OUTPUT"),
        V("xRise", "BOOL", "VAR_OUTPUT"),
        V("xFall", "BOOL", "VAR_OUTPUT"),
        V("fbSr", "SR"),
        V("fbRs", "RS"),
        V("fbCtu", "CTU"),
        V("fbCtd", "CTD"),
        V("fbRise", "R_TRIG"),
        V("fbFall", "F_TRIG"),
    ],
    doc=__doc__ or "",
)
