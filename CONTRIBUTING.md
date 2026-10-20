# Правила разработки

## Окружение

```
python -m venv .venv --system-site-packages
.venv\Scripts\python -m pip install -r requirements-dev.txt -e .
git clone https://github.com/kr0nsch/s7-to-codesys.git .cache/s7-to-codesys@2285760c
git -C .cache/s7-to-codesys@2285760c checkout 2285760c1c99ce4218d5356c75e93111828f8e3b
python tools/fetch_xsd.py          # XSD V19/V21 в .cache/xsd (по SHA-256)
```

Клон s7-to-codesys — только для чтения: проверяются SHA и пустой `git status`. Живой рабочий
каталог s7-to-codesys не используется.

## Проверки перед коммитом

```
python -m ruff check . && python -m ruff format --check . && python -m mypy
python -m pytest
python tools/gen_docs.py --check            # MAPPING.md и RULES.md из YAML
python tools/corpus/gen_scenarios.py --check
python tools/make_data.py --check           # данные сайта
```

Локально, при установленном CODESYS 3.5.17.30: `python -m pytest -m codesys tests/codesys`.
Рантайм Control Win общий для нескольких проектов: блокировка — `%LOCALAPPDATA%\plc-tools\codesys-runtime.lock`;
чужой рантайм не перезапускать и не останавливать.

## Правила

- Коммиты — Conventional Commits на русском (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), небольшие.
- Golden (`tests/golden/tia`) пересобирается `UPDATE_GOLDEN=1 python -m pytest tests/formats` отдельным
  коммитом.
- Трассы CODESYS (`oracle-codesys.*`) и экспорты (`source.cds.xml`) коммитятся побайтно, только свои.
- В репозиторий не кладутся: XSD и документы Siemens, код с лицензией GPL/LGPL или без лицензии, эталоны
  чужих экспортов — только `.cache/` по SHA-256.
- Каждое утверждение о TIA/S7 — с источником; непроверенное так и называется (`docs/ASSUMPTIONS.md`).
- Новое правило C2S7-* — с корпусом `tests/corpus/<id>/{pos,neg}`, описанием и источником.
- Допущения и решения — в `docs/ASSUMPTIONS.md`, план P1 — в `docs/ROADMAP.md`.
