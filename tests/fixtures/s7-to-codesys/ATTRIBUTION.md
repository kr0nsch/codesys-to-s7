# Вход кейса 1 «Кольцо S7 → CODESYS → S7»

Файлы взяты из [kr0nsch/s7-to-codesys](https://github.com/kr0nsch/s7-to-codesys) @
`2285760c1c99ce4218d5356c75e93111828f8e3b` (выпуск 1.0.0), MIT, Copyright (c) 2026 kr0nsch —
LICENSE рядом. Изменений нет.

| Путь | Что это | Откуда |
|---|---|---|
| `src/` | выход `s7conv build-corpus`: 19 POU, 7 объектов S7Compat, 7 GVL, 7 DUT | `src/` репозитория |
| `scenarios/*.csv`, `scenarios/README.md` | 6 наборов сценариев, 39 сценариев, 263 строки | `scenarios/` |
| `tools/codesys/config.json` | задачи корпуса (`modes.normal.tasks`) | `tools/codesys/config.json` |
| `tasks.json` | задачи с полями `sources` («Main (OB1)») и `obs` (номера и виды OB) | `python -m s7conv convert samples/scl --out <каталог> --timers s7compat` на том же коммите (20.10.2026) |

Исходный SCL корпуса (`samples/scl/`), с которым кольцо сравнивает результат, в репозиторий не
копируется: тесты читают его из клона `.cache/s7-to-codesys@2285760c` (проверка SHA и пустого
`git status`, иначе код 2 — `c2s7.verify.s7conv_clone`).
