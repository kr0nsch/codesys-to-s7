# Изменения

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — [SemVer](https://semver.org/lang/ru/).

## [0.1.0] — 2026-10-20

Первый выпуск: MVP по ТЗ (этапы 0, A–D; P1 не входит — `docs/ROADMAP.md`).

### Добавлено

- Пакет и CLI `c2s7`: `inventory`, `analyze`, `migrate`, `verify --roundtrip`, `probe`, `render`,
  `explain`, `site`; коды выхода 0/1/2.
- Входы: PLCopen XML CODESYS 3.5 (ST, LD, FBD, CFC, SFC, IL; методы, свойства, действия, GVL, DUT,
  задачи), ST-раскладка plc-repo-template, одиночный `.st`, `--io-map`.
- Свой фронтенд ST на lark; понижения IL/LD/FBD/CFC/SFC в ST AST; свёртка переходов.
- Выход: внешние исходники TIA (`.scl/.db/.udt`, UTF-8 BOM, CRLF), SimaticML FlgNet V19/V21 для LD/FBD
  на закрытом подмножестве со своим валидатором и проверкой XSD, `PLCTags.xlsx`, тела OB и
  `TASKS.md`, CodesysCompat `CDS_SR/CDS_RS`, файлы кольца, `MIGRATION_REPORT.{md,json,html}`,
  `trace.json`, пробник `probe/`, детерминированный zip.
- 57 правил переносимости C2S7-* с корпусом pos/neg и моделью трудозатрат (не калибрована).
- `c2s7.sim` — интерпретатор ST с семантикой CODESYS по пробе M0.
- Кейс 1 «Кольцо S7 → CODESYS → S7» через s7-to-codesys @ 2285760c; кейс 2 — корпус «все языки»
  ВОС «Заречная» (13 POU), собранный в CODESYS 3.5.17.30, с трассами Control Win.
- Просмотрщик на GitHub Pages: кейсы, схемы SVG, находки, галерея ловушек, переключатель S7-1200/1500.
