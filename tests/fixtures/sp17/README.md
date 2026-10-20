# Экспорты CODESYS 3.5.17.30 (свои, MIT)

PLCopen XML, которые CODESYS V3.5 SP17 Patch 3 (сборка ОВЕН) записал 20.10.2026 на машине автора:

- `form_*.xml` — объекты, созданные скриптингом (`tools/probes/cds_probe.py`, шаг forms): GVL с
  RETAIN/PERSISTENT, DUT, ФБ с методом/свойством/действием, программа, экспорт Application
  (с задачами) с текстом объявлений и без;
- остальные — экспорт POU пробы M0 после `import_xml` → сборка (`tools/probes/run_probes.py import`):
  входы строит `tools/corpus/builder.py` из `tools/probes/probe_specs.py`.

Файлы не правились (BOM, отступы и порядок атрибутов — как у CODESYS). Используются как фикстуры
разборщика PLCopen (`c2s7.ingest.plcopen`) и семантического сравнения «спецификация ↔ экспорт».
Лицензия — MIT (LICENSE в корне репозитория).
