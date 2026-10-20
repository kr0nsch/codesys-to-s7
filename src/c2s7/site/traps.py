"""«Галерея ловушек» (ТЗ §9): фрагмент CODESYS, факт о поведении S7 с источником [H], SCL на выходе c2s7
(считается при сборке сайта тем же конвертером) и свидетельство из CODESYS Control Win.
"""

from __future__ import annotations

from dataclasses import dataclass

LAD_REF = "https://cache.industry.siemens.com/dl/files/822/45523822/att_82001/v1/s7kop__b.pdf"
S1200 = "https://cache.industry.siemens.com/dl/files/465/36932465/att_106119/v1/s71200_system_manual_en-US_en-US.pdf"
COMPARE = "https://cache.industry.siemens.com/dl/files/648/109797648/att_1067421/v1/s71500_compare_table_en.pdf"


@dataclass(frozen=True)
class Trap:
    id: str
    title: str
    codesys: str  # ST-фрагмент: объявления + тело (FUNCTION_BLOCK FB_Trap)
    s7_fact: str
    s7_source: str
    evidence: str
    verdict: str
    profile: str = "s7-1500"


TRAPS: list[Trap] = [
    Trap(
        "srrs",
        "SR и RS — одноимённые, но с противоположным приоритетом",
        "FUNCTION_BLOCK FB_Trap\nVAR_OUTPUT\n    xSr, xRs : BOOL;\nEND_VAR\nVAR\n    fbSr : SR;\n    fbRs : RS;\nEND_VAR\n"
        "fbSr(SET1 := TRUE, RESET := TRUE, Q1 => xSr);\nfbRs(SET := TRUE, RESET1 := TRUE, Q1 => xRs);\nEND_FUNCTION_BLOCK\n",
        "У S7 SR — сброс доминирует, RS — установка доминирует (у CODESYS наоборот); в SCL инструкций SR/RS нет.",
        LAD_REF + " (§1.10–1.11); " + COMPARE + " (с. 15)",
        "Проба M0 в CODESYS Control Win 3.5.17.30: SR(1, 1) → TRUE, RS(1, 1) → FALSE. c2s7 подставляет блоки "
        "CodesysCompat CDS_SR/CDS_RS с семантикой CODESYS (C2S7-SEM-SRRS).",
        "review",
    ),
    Trap(
        "selfreset",
        "Самосбрасывающийся таймер t(IN := NOT t.Q)",
        "FUNCTION_BLOCK FB_Trap\nVAR_OUTPUT\n    xPulse : BOOL;\nEND_VAR\nVAR\n    fbPulse : TON;\nEND_VAR\n"
        "fbPulse(IN := NOT fbPulse.Q, PT := T#500MS);\nxPulse := fbPulse.Q;\nEND_FUNCTION_BLOCK\n",
        "S7-1200 обновляет Q и ET и при вызове, и при прямом чтении членов Q/ET — импульс может не появиться.",
        S1200 + " (§7.2, с. 186–187)",
        "Трасса Control Win (R2) корпуса FB_TimeIdioms: Q = TRUE ровно на один вызов, 303/303 циклов совпали с c2s7.sim. "
        "c2s7 переписывает идиому на выход вызова Q => (C2S7-SEM-TIMER-Q).",
        "review",
    ),
    Trap(
        "ftrig",
        "F_TRIG — не ловушка",
        "FUNCTION_BLOCK FB_Trap\nVAR_INPUT\n    xClk : BOOL;\nEND_VAR\nVAR_OUTPUT\n    xFall : BOOL;\nEND_VAR\nVAR\n"
        "    fbF : F_TRIG;\nEND_VAR\nfbF(CLK := xClk, Q => xFall);\nEND_FUNCTION_BLOCK\n",
        "F_TRIG S7 на первом вызове с CLK = FALSE спада не даёт.",
        "s7-to-codesys @ 2285760c docs/TEST_REPORT.md (StandardFTrigMatchesS7)",
        "Проба M0: F_TRIG Standard 3.5.17 на первом вызове с CLK = FALSE → FALSE, как у S7. Перенос — auto.",
        "auto",
    ),
    Trap(
        "time24d",
        "TIME больше 24 суток",
        "FUNCTION_BLOCK FB_Trap\nVAR_INPUT\n    tIn : TIME;\nEND_VAR\nVAR_OUTPUT\n    xLong : BOOL;\nEND_VAR\n"
        "xLong := tIn > T#30D;\nEND_FUNCTION_BLOCK\n",
        "Time S7 — ±24d20h31m23s647ms; TIME CODESYS — 32 бита без знака (до 49d17h). Длиннее — LTime (S7-1500).",
        S1200 + "; " + COMPARE,
        "Проба M0: T#0MS − T#1MS = 49d17h2m47s295ms (перенос без знака). c2s7: на S7-1500 литерал → LT#30D, "
        "на S7-1200 — impossible (C2S7-TYPE-TIME).",
        "review",
    ),
    Trap(
        "iw5",
        "%IW5 — это не %IW5",
        "FUNCTION_BLOCK FB_Trap\nVAR_OUTPUT\n    iRaw : INT;\nEND_VAR\nVAR\n    iIn AT %IW5 : INT;\nEND_VAR\n"
        "iRaw := iIn;\nEND_FUNCTION_BLOCK\n",
        "У S7 адрес — номер байта: %IW5 — байты 5–6, порядок байтов big-endian. У CODESYS %IW5 — слово 5 (байты 10–11), "
        "little-endian.",
        S1200 + " (разд. 4.4); s7-to-codesys docs/MAPPING.md «Адресная модель»",
        "Проба M0: после %MW0 := 16#0108 бит %MX1.0 = TRUE (байтовая адресация битов, little-endian). c2s7: "
        "%IW5 → %IW10, наложения разной ширины — C2S7-ADDR-OVERLAP.",
        "review",
    ),
    Trap(
        "round",
        "REAL_TO_INT(2.5)",
        "FUNCTION_BLOCK FB_Trap\nVAR_OUTPUT\n    i25, im25 : INT;\nEND_VAR\ni25 := REAL_TO_INT(2.5);\nim25 := REAL_TO_INT(-2.5);\n"
        "END_FUNCTION_BLOCK\n",
        "Поведение S7 на половине в найденных источниках противоречиво — вынесено в пробник P01.",
        "codesys-to-s7.md R§4 (противоречиво) → probe/P01",
        "Проба M0: CODESYS 2.5 → 3, −2.5 → −3 (половина от нуля). Класс verify (C2S7-SEM-ROUND), пробник для TIA.",
        "verify",
    ),
]
