"""FB_TimeIdioms — таймеры промывочного насоса (ST, FUNCTION_BLOCK).

Поведение (модель scenarios/reference/model_FB_TimeIdioms.py):
- fbPulse(IN := NOT fbPulse.Q, PT := T#500MS) — самосбрасывающийся таймер: Q = TRUE ровно на один вызов,
  когда ET ≥ 500 мс, следующий вызов сбрасывает таймер (IN = FALSE), ещё следующий — запускает снова;
  xPulse := fbPulse.Q (C2S7-SEM-TIMER-Q: S7-1200 обновляет Q и при чтении члена);
- xEarly := fbDelay.Q до вызова fbDelay — значение прошлого вызова; xLate := fbDelay.Q после вызова
  fbDelay(IN := xIn, PT := T#1S) — TON: Q, когда xIn держится ≥ 1 с;
- xLong := tIn > T#30D — литерал больше диапазона Time S7 (±24d20h): на S7-1500 → LTime, на S7-1200 —
  impossible (C2S7-TYPE-TIME). TIME CODESYS — 32 бита без знака.
"""

from builder import Pou, St, V

POU = Pou(
    "FB_TimeIdioms",
    "functionBlock",
    St(
        "fbPulse(IN := NOT fbPulse.Q, PT := T#500MS);\n"
        "xPulse := fbPulse.Q;\n"
        "xEarly := fbDelay.Q;\n"
        "fbDelay(IN := xIn, PT := T#1S);\n"
        "xLate := fbDelay.Q;\n"
        "xLong := tIn > T#30D;\n"
    ),
    [
        V("xIn", "BOOL", "VAR_INPUT"),
        V("tIn", "TIME", "VAR_INPUT"),
        V("xPulse", "BOOL", "VAR_OUTPUT"),
        V("xEarly", "BOOL", "VAR_OUTPUT"),
        V("xLate", "BOOL", "VAR_OUTPUT"),
        V("xLong", "BOOL", "VAR_OUTPUT"),
        V("fbPulse", "TON"),
        V("fbDelay", "TON"),
    ],
    doc=__doc__ or "",
)
