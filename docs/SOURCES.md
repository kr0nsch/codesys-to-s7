# Источники

Факты о TIA Portal и S7 даны со ссылкой; материалы Siemens — только ссылками (в репозитории их нет).
Даты сверки — 19–20.10.2026.

## Siemens (документы, только ссылки)

| Документ | Что взято |
|---|---|
| Comparison list S7-1200/1500, 05/2021 — https://cache.industry.siemens.com/dl/files/648/109797648/att_1067421/v1/s71500_compare_table_en.pdf | языки по CPU (STL/GRAPH/CFC — только 1500), SR/RS в SCL нет (с. 15), REF_TO |
| LAD-справочник 05/2010 — https://cache.industry.siemens.com/dl/files/822/45523822/att_82001/v1/s7kop__b.pdf | SR — сброс доминирует, RS — установка (§1.10–1.11), ENO = EN AND NOT ошибка (прил. C.1) |
| S7-1200 System Manual 04/2012 — https://cache.industry.siemens.com/dl/files/465/36932465/att_106119/v1/s71200_system_manual_en-US_en-US.pdf | Q/ET таймера при чтении членов (§7.2, с. 186–187), беззнаковый CTD, диапазон Time, адресация (разд. 4.4) |
| XSD SimaticML (копии из установок TIA) в dotnetprojects/DotNetSiemensPLCToolBoxLibrary @ `bbe5beccbadcf7497408e92883e260cc5024a874` | структура FlgNet, Interface, матрица пространств имён по версиям; скачивается `tools/fetch_xsd.py` по SHA-256 в `.cache/` |

## CODESYS

| Источник | Что взято |
|---|---|
| Справка CODESYS SFC — https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_sequence_of_processing.html | порядок цикла SFC |
| https://content.helpme-codesys.com/en/CODESYS%20SFC/_cds_sfc_action_qualifier.html | квалификаторы действий |
| https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_project_export_import.html | PLCopen — «100% compatibility is thus not guaranteed» |
| https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_cmd_export_io_mapping_csv.html | экспорт карты ввода-вывода в CSV |
| Пробы на этой машине (CODESYS 3.5.17.30, Control Win) | всё поведение в `PROBES.md`, трассы корпуса и кольца |

## Открытый код и образцы

| Источник | Лицензия | Использование |
|---|---|---|
| kr0nsch/s7-to-codesys @ `2285760c1c99ce4218d5356c75e93111828f8e3b` | MIT | вход кейса 1 (`tests/fixtures/s7-to-codesys`, с ATTRIBUTION.md), s7conv и stsim из клона в `.cache/` (не копируются) |
| kr0nsch/plc-repo-template @ `da0fc91771a0ecb5ba0df45d636e24c8d9711f9d` | MIT | `tools/codesys/` (копия, ATTRIBUTION.md) |
| bulaofen0036-coder/TIA_Portal_Openness_MCP @ `e131b2570c75c323bc330e9793c293e4b5f231c6` | MIT | эталонный набор FlgNet (только `.cache/`, [M]) |
| eponce00/tiaopen-mcp @ `e2b26de46306669ba87e6b7c246def981b76ca72` | MIT | шаблоны с токенами — только справка [M] |
| Chamoswor/s7-lint-vscode @ `0735f8ff04ea8496175e8be713d5e004ee5d1e12` | Apache-2.0 | имена частей FBD `A/O/X` из реестра инструкций (только `.cache/`) |
| johannesPettersson80/trust-platform @ `161992b5` | — | судьба VAR программы при экспорте в SCL (только чтение кода) |

## Внутренние исследования серии

`domestic-plc-gaps/migration/research/codesys-to-s7.md` (R§), конспект экспериментов проекта 00
(E§), `migration/prompts/00-INDEX.md` §4 — общие решения семейства (классы, ядро отчёта, трассы,
блокировка рантайма).
