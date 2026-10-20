# Вход c2s7: PLCopen XML CODESYS 3.5.17 и ST-раскладка

Что c2s7 читает и в какой форме. Источники: собственные экспорты CODESYS 3.5.17.30 на машине автора
(`tests/fixtures/sp17/`, пробы M0 — [PROBES.md](PROBES.md)), канон addData 3S проекта plcopen-diff,
публичные экспорты (только для чтения формы). Всё, что не подтверждено экспортом, помечено.

## Решение по языкам (по итогам проб M0, 20.10.2026)

| Язык | Импорт в CODESYS (G/N) | Вход c2s7 | Корпус |
|---|---|---|---|
| ST | G | PLCopen `<ST>`, ST-раскладка, одиночный `.st` | `import_xml` → сборка → экспорт |
| FBD | G (без EN/ENO) | `<FBD>`, сети по `localId div 10^10` | то же |
| LD | G (без бокса EN/ENO) | `<LD>`, сети по парам `comment` + `networktitle` | то же |
| CFC | G | addData `…/cfc`, порядок `executionOrderId` | то же |
| SFC | G (без entry/exit) | `<SFC>` + `<actions>` | то же |
| IL | **N** | текст IL (`<IL>` публичных экспортов, `.il`, тело в раскладке) → ST AST | только текстовый корпус для `c2s7.sim` (запасной путь (б) ТЗ M0) |

Критерии §11 по IL меняются по этому решению: корпус P0 — 13 POU, из них 11 принимает CODESYS;
2 POU на IL проверяются разбором текста и `c2s7.sim`. Бокс EN/ENO (LD/FBD) и entry/exit SFC в
корпус CODESYS не входят; их перевод проверяется на NetIR/SfcIR, построенных напрямую (unit- и
property-тесты), правило C2S7-GFX-ENO — на корпусе правил.

## Размещение объектов

Три размещения POU (канон plcopen-diff §4/§7), c2s7 читает все:
1. `project/types/pous/pou`, `types/dataTypes/dataType` — экспорт выбранных объектов;
2. `instances/configurations/configuration/resource/addData/data[…/pou]` — полный экспорт (Astra.IDE);
3. `project/addData/data[@name="…/plcopenxml/application"]/resource/{task, globalVars, addData/data[…/pou|…/datatype|…/libraries]}` —
   экспорт узла Application в CODESYS 3.5.17.30 (проверено: `tests/fixtures/sp17/form_Application.xml`).

GVL в экспорте выбранных объектов — `project/addData/data[…/globalvars]/globalVars`.

## Объявления

- Стандартный `<interface>`: `inputVars`, `outputVars`, `inOutVars`, `localVars`, `tempVars`,
  `externalVars`, `globalVars`, `returnType`; типы — элементарные элементы (`<BOOL/>`, `<TIME/>`),
  `<string length>`, `<wstring>`, `<array><dimension lower upper/>…<baseType>`, `<derived name>`,
  `<pointer>`; начальное значение — `initialValue/simpleValue@value` (текст ST), `arrayValue`, `structValue`.
- addData `…/interfaceasplaintext` (экспорт с «declarations as plain text») — объявление ST как в
  IDE, без потерь (комментарии, прагмы, AT). Если есть — c2s7 разбирает его, а не XML.
- RETAIN/PERSISTENT GVL — addData `…/mixedattrsvarlist`: по `globalVars` с атрибутами `retain`,
  `persistent`, `constant` на каждую секцию. Список Persistent Variables экспортируется одним
  `globalVars persistent="true"` с атрибутами `order_in_persistent_editor`.
- Атрибуты (`qualified_only` и др.) — addData `…/attributes/Attributes/Attribute@Name`.
- Методы и свойства — addData `…/method/Method`, `…/property/Property/{GetAccessor,SetAccessor}`;
  действия — `pou/actions/action`.

## Тела графических языков

**LD** (экспорт 3.5.17.30): одна `leftPowerRail localId="0"`, сквозная нумерация `localId`, сеть
начинается парой `comment` + `vendorElement` с `ElementType = networktitle` (заголовок — в
`alternativeText`). `contact@negated/edge`, `coil@negated/storage` (`set`, `reset`). Параллель —
несколько `connection` в одном `connectionPointIn`. Все `position` = 0,0.

**FBD**: первый элемент — `vendorElement` «FBD Implementation Attributes»; сеть k — элементы с
`localId` от k·10^10; заголовок сети — `vendorElement networktitle`, метка — `label` перед ним.
Блок: `block@typeName[@instanceName]`, входы `inputVariables/variable@formalParameter[@negated]`,
вызов — addData `…/fbdcalltype` (`operator`, `function`, `functionblock`). Выход блока в соединении
— `connection@formalParameter="Out1"` (у оператора) или имя выхода ФБ. `jump@label`, `return`;
отрицание условия перехода — только блоком NOT (атрибут `negated` у `jump` CODESYS отвергает).

**CFC**: тело `<ST>` пустое, схема — addData `…/cfc/CFC` (`page-oriented="true"` и `vendorElement`
`…/cfcpage` у страничного). Порядок — `executionOrderId` у блоков и выходов. Провод идёт через
`connector name=""`: connector → источник (`formalParameter` = выражение входной переменной, `""` у
выхода оператора, имя пина у ФБ), вход блока → connector. Входы операторов — `In1…InN`.

**SFC**: `step@name[@initialStep]`, `transition` с `condition` (через `inVariable` или встроенный
ST), `selectionDivergence/Convergence`, `simultaneousDivergence/Convergence`, `jumpStep@targetName`,
`actionBlock/action@qualifier@duration` + `reference@name`. Атрибуты элементов — addData
`…/sfc/element/attributes/attribute@guid`:

| GUID | Смысл | Основание |
|---|---|---|
| `38391c6d-6d4a-42f8-8ee7-9f45e5adafa8` | имя (шаг, переход, действие) | свои экспорты |
| `6844a48e-46c2-4cc8-a185-a478f3b99cc0` | начальный шаг (TRUE/FALSE) | свои экспорты |
| `700a583f-b4d4-43e4-8c14-629c7cd3bec8` | действие шага (не IEC) | публичные экспорты, проба M0 (G) |
| `e174fc0d-80b0-4a9e-a530-ca239c249a50` | квалификатор действия | свои экспорты |
| `01580b27…`, `bc882c11…`, `62e1754b…`, `8294df19…`, `23bdaa98…` | служебные, смысл не установлен [L] | — |

Флаги SFC POU — addData `…/sfcsettings` (библиотека IecSfc, `Flags`). Entry/exit-действия в
PLCopen не найдены (N).

**IL**: стандартный `<IL><xhtml>`; CODESYS с выключенной опцией IL его пропускает.

## Задачи и библиотеки

`task@name@interval@priority` (интервал — `PT0.01S`) + addData `…/tasksettings/TaskSettings`
(`KindOfTask` = Cyclic | Freewheeling | Event | Status, `Interval`, `IntervalUnit`), программы —
`pouInstance@name` в порядке вызова. Библиотеки — addData `…/libraries/Libraries/Library@Name@Namespace@DefaultResolution`.

## Ввод-вывод: `--io-map`

«Export mappings to CSV» устройства CODESYS: разделитель — системный разделитель списков, у
неуникальных имён суффикс `@<n>` (справка CODESYS). Колонки справка не описывает; в c2s7 читаются
строки с непустыми «Variable» и «Address» (имена колонок ищутся без учёта регистра, допускаются
«Переменная»/«Адрес») — формат CSV своего проекта сверить [L]. Без `--io-map` — находка
C2S7-IO-NOMAP и пустой `IO_MAP.csv`.

## ST-раскладка

Контракт — `docs/LAYOUT.md` s7-to-codesys: `src/POUs/<имя>/<имя>.decl.st` + `.impl.st`, `src/GVLs/*.gvl.st`,
`src/DUTs/*.dut.st`, методы `*.method.decl.st`. Задачи — `tasks.json` (выход `s7conv convert`) или
`tools/codesys/config.json` (`modes.normal.tasks`); поле `sources` вида `"Main (OB1)"` связывает
программу с исходным OB (используется в кольце, `--ob-from-tasks`).
