IF GVL_S7Clock.xSimulation THEN
    F_S7Now := GVL_S7Clock.tSimNow;
ELSE
    F_S7Now := TIME();
END_IF
