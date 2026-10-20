# Происхождение `tools/codesys/`

Файлы `cds.py`, `cds_common.py`, `cdshost/`, `build.py`, `check_sources.py`, `export_sources.py`,
`import_sources.py`, `library_repo.py`, `make_library.py`, `run_tests.py`, `stlayout.py` скопированы
без изменений из репозитория [kr0nsch/plc-repo-template](https://github.com/kr0nsch/plc-repo-template)
@ `da0fc91771a0ecb5ba0df45d636e24c8d9711f9d` (MIT, Copyright (c) 2026 kr0nsch). Класс `FileLock` в
`cdshost/cli.py` совпадает побайтно с s7-to-codesys @ `2285760c` — это общий протокол блокировки
рантайма семейства миграции.

Изменён только `config.json` (имя проекта, пустой список задач режима `normal`). Свои файлы c2s7:

| Файл | Назначение |
|---|---|
| `lock.py` | обёртки FileLock с путями блокировок рантайма и медиа-кита |
| `online.py` | прогон скрипта CODESYS под блокировкой рантайма; общий рантайм не перезапускается |
| `c2s7_online.py` | скрипт CODESYS (IronPython 2.7): проект из PLCopen/ST, сборка, Control Win, чтение значений |
| `trace.py` | съёмка трасс R2 (`oracle-codesys.csv`) |
