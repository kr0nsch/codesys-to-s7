# Что дальше

Версия 0.1.0 — MVP по ТЗ (список «не срезается»). Этап E (P1) в эту версию не вошёл по порядку среза
ТЗ §12; ниже — что именно и в каком порядке.

## P1 (не в 0.1.0)

| Пункт | Сейчас | План |
|---|---|---|
| Корпус 13 → 20 POU | 13 POU (11 в CODESYS + 2 IL текстом) | FB_TextMsg, PRG_Main, FB_DosingFbd, FB_StartTimer, FB_MacroCfc, PRG_ParallelSfc, FB_Pump EXTENDS FB_Device |
| CFC → FBD | CFC → SCL | FlgNet FBD из NetIR CFC с порядком выполнения |
| SFC: L/D/SD/DS/SL, флаги | C2S7-GFX-SFCQ (manual) | разложение на таймеры |
| GRAPH (1500) | `--sfc graph` → находка, выдаётся автомат SCL | Graph v6 по XSD, экспериментально |
| SD (`.s7dcl/.s7res`) и plc-code | — | SD для LAD/FBD (V20+), проверка `plc code` |
| CodesysCompat P1 | только CDS_SR/CDS_RS | CDS_TON/TOF/TP, CDS_F_TRIG, Util (BLINK, HYSTERESIS, RAMP, PID…) со сверкой в Control Win |
| ООП | план уплощения в MANUAL_STEPS (C2S7-OOP) | статика FB → UDT, METHOD → FC с InOut self, PROPERTY, EXTENDS |
| Профили V15.1–V18 | матрица пространств имён есть, вывод — только SCL | SimaticML по схемам без эталона |
| Кейсы 3–4 | — | plc-process-lib (FB_Motor), чужие экспорты (SP18, Astra.IDE CFC, TwinCAT SFC) |
| `tools/tia/Import-C2S7.ps1` | — | минимальный импорт через Openness без сниппетов Siemens |
| Перезакрепление s7-to-codesys | @ 2285760c (1.0.0) | на тег 1.1.0 отдельным коммитом, пересборка golden кольца |
| extras.yml | stsim — в основном CI | plc-code, s7-lint, кейс 4 |

## NICE

Кольцо графики через импортёр SimaticML s7-to-codesys; «Вставьте свой ST» на Pyodide; IL → STL;
NVT для ENUM; `c2s7 probe apply RESULTS.csv`; оценка Retain против памяти CPU.
