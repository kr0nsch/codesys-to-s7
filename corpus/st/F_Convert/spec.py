"""F_Convert — пересчёт аналоговой уставки дозатора коагулянта (ST, FUNCTION).

Поведение (по нему считает модель scenarios/reference/model_F_Convert.py):
- результат функции — REAL_TO_INT(rIn): половина округляется от нуля (2.5 → 3, −2.5 → −3; проба M0);
- iSum := iA + iB с переносом INT (32767 + 1 = −32768);
- iQuot := iA / iB с отбрасыванием дробной части к нулю, при iB = 0 — 0 (делитель-переменная → C2S7-SEM-DIV0);
- iMux := MUX(iSel, 10, 20, 30), iSel ∈ 0…2;
- iLim := LIMIT(iMn, результат, iMx); при MN > MX результат — MX (проба M0: LIMIT(10, 5, 0) = 0).
"""

from builder import Pou, St, V

POU = Pou(
    "F_Convert",
    "function",
    St(
        "F_Convert := REAL_TO_INT(rIn);\n"
        "iSum := iA + iB;\n"
        "IF iB <> 0 THEN\n    iQuot := iA / iB;\nELSE\n    iQuot := 0;\nEND_IF\n"
        "iMux := MUX(iSel, 10, 20, 30);\n"
        "iLim := LIMIT(iMn, F_Convert, iMx);\n"
    ),
    [
        V("rIn", "REAL", "VAR_INPUT"),
        V("iA", "INT", "VAR_INPUT"),
        V("iB", "INT", "VAR_INPUT"),
        V("iSel", "INT", "VAR_INPUT"),
        V("iMn", "INT", "VAR_INPUT"),
        V("iMx", "INT", "VAR_INPUT"),
        V("iSum", "INT", "VAR_OUTPUT"),
        V("iQuot", "INT", "VAR_OUTPUT"),
        V("iMux", "INT", "VAR_OUTPUT"),
        V("iLim", "INT", "VAR_OUTPUT"),
    ],
    return_type="INT",
    doc=__doc__ or "",
)
