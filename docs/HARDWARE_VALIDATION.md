# Проверка на TIA Portal и PLCSIM — процедура для человека с TIA

У автора TIA Portal, PLCSIM и SIMATIC AX нет. Всё, что ниже, — поставляемая процедура, а не
доказательство готовности. Результаты записываются в `docs/VALIDATION_LOG.md` (дата, версии, ошибки
дословно) и в `probe/RESULTS.csv`.

Нужно: TIA Portal V19 или V21 со STEP 7 Professional, PLCSIM (для S7-1500 — PLCSIM или PLCSIM
Advanced), ≈ 2–3 часа.

## 1. Внешние исходники (CPU 1511-1 PN и CPU 1214C)

```
c2s7 migrate corpus/zarechnaya.xml --out out/zar-1500 --cpu s7-1500 --tia V21
c2s7 migrate corpus/zarechnaya.xml --out out/zar-1200 --cpu s7-1200 --tia V19
```

1. Новый проект, CPU 1511-1 PN (и отдельно 1214C).
2. Program blocks → External source files → Add new external file → все `tia/compat/*.scl`, затем
   `tia/sources/*` по порядку номеров.
3. Каждый файл → Generate blocks from source. Записать ошибки дословно.
4. Compile → Software (rebuild all). Записать ошибки и предупреждения.

## 2. SimaticML и теги

1. Блоки LAD/FBD — `tia/simaticml/*.xml` через Openness (`tools/tia/Import-C2S7.ps1` — P1, не
   написан; вручную — скриптом Openness `PlcBlockComposition.Import`). Культура текстов — en-US.
2. Теги — `tia/tags/PLCTags.xlsx`: PLC tags → Import (лист «PLC Tags» и «User constants»).
3. OB — по `roundtrip/TASKS.md`: Add new block → Organization block нужного типа и номера, тело —
   из `tia/ob/OB_<Задача>.body.scl`.

## 3. Пробник

`probe/` из `migrate` (или `c2s7 probe out/zar-1500`): каждый `P*.scl` → блок, вызов в OB1,
PLCSIM, значения выходов → `probe/RESULTS.csv` (`observed`: `ok`, `error:<текст>`,
`value:<значение>`).

## 4. Поведение (PLCSIM, ≤ 20 мин)

Сценарии `scenarios/F_Convert.csv`, `FB_Latch.csv`, `PRG_Permissives.csv` (короткие, без таймеров
длиннее 2 с): вход строки → вызов → сравнение выходов с CSV. Расхождения сверить с
`EQUIVALENCE.md` и классом конструкции в отчёте (verify — ожидаемо возможны).

## 5. Шаг владельца в CODESYS (IL)

IL в CODESYS 3.5.17 выключен по умолчанию и из PLCopen не импортируется (M0: N). Чтобы проверить
корпус IL в CODESYS: Tools → Options → FBD, LD and IL → включить IL; затем импортировать
`corpus/zarechnaya.xml` — POU `FB_PulseCountIL` и `F_ScaleIL`. Опция пользовательская и общая для
всех проектов машины: включить один раз, факт и дату записать сюда.
