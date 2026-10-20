// Просмотрщик миграции c2s7: данные — data/*.json (c2s7 site), без сетевых обращений к другим доменам.
const OUTCOMES = ["auto", "review", "verify", "manual", "impossible"];
const state = { index: null, caseId: "ring", cpu: "s7-1500", data: null, pou: null, tab: "equiv" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const pre = (s) => `<pre>${esc(s)}</pre>`;

async function json(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

function renderCases() {
  $("cases").innerHTML = state.index.cases
    .map((c) => `<button data-case="${c.id}" class="${c.id === state.caseId ? "on" : ""}" ${c.planned ? "disabled title='P1'" : ""}>${esc(c.title)}</button>`)
    .join("");
  $("cases").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { state.caseId = b.dataset.case; load(); }));
}

function renderSummary() {
  const c = state.index.cases.find((x) => x.id === state.caseId);
  const d = state.data;
  $("about").textContent = c.about;
  const t = d.totals.by_outcome;
  const total = OUTCOMES.reduce((s, k) => s + (t[k] || 0), 0);
  $("counters").innerHTML = OUTCOMES.map((k) => {
    const pct = total ? Math.round((100 * (t[k] || 0)) / total) : 0;
    return `<div class="counter o-${k}" data-outcome="${k}"><b>${t[k] || 0}</b><span>${k} · ${pct}%</span></div>`;
  }).join("");
  $("effort").textContent = `Трудозатраты на ручные шаги: P50 ${d.effort.p50_h} ч, P90 ${d.effort.p90_h} ч (${d.effort.calibration}). Профиль: ${d.profile}.`;
  $("verdict").textContent = `Вердикт: ${d.verdict}`;
}

function renderTree() {
  const order = { ST: 0, FBD: 1, LD: 2, CFC: 3, SFC: 4, IL: 5 };
  const pous = [...state.data.pous].sort((a, b) => (order[a.language] ?? 9) - (order[b.language] ?? 9) || a.name.localeCompare(b.name));
  if (!state.pou || !pous.find((p) => p.name === state.pou)) state.pou = pous[0]?.name;
  $("pous").innerHTML = pous
    .map((p) => `<li data-pou="${esc(p.name)}" class="${p.name === state.pou ? "on" : ""}"><span class="dot o-${p.outcome}"></span>${esc(p.name)}<span class="lang">${p.language}</span></li>`)
    .join("");
  $("pous").querySelectorAll("li").forEach((li) => li.addEventListener("click", () => { state.pou = li.dataset.pou; renderTree(); renderPou(); }));
}

function renderPou() {
  const p = state.data.pous.find((x) => x.name === state.pou);
  if (!p) return;
  $("src-title").textContent = `CODESYS · ${p.language}`;
  $("src").innerHTML = (p.svg_source ? `<img src="${p.svg_source}" alt="Схема ${esc(p.name)} в CODESYS">` : "") + pre(p.source);
  const kinds = { scl: "SCL (внешний исходник)", simaticml: "LAD/FBD (SimaticML FlgNet)", ob: "тело OB (SCL)", none: "—" };
  $("tgt-title").textContent = `TIA Portal · ${kinds[p.target_kind] || p.target_kind}`;
  $("tgt").innerHTML = (p.svg_target ? `<img src="${p.svg_target}" alt="Схема ${esc(p.name)} в TIA (построена c2s7)">` : "") + pre(p.target);
  $("findings").innerHTML = p.findings.length
    ? p.findings
        .map((f) => `<div class="card o-${f.outcome}"><h3>${esc(f.title)}</h3><div class="rule">${f.rule} · ${f.outcome}${f.line ? ` · стр. ${f.line}` : ""}</div><p>${esc(f.why)}</p><p><b>Что делать:</b> ${esc(f.fix)}</p></div>`)
        .join("")
    : "<p class='note'>Находок нет.</p>";
}

function table(head, rows) {
  return `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function equivTab() {
  const e = state.index.equivalence;
  if (state.caseId === "ring") {
    const r = e.ring;
    if (!r) return "<p>Нет данных прогона (tools/make_data.py).</p>";
    const kinds = Object.entries(r.ring.by_kind).map(([k, v]) => [k, `${v.matched}/${v.total}`]);
    let html = `<p>Кольцо S7 → CODESYS → S7 (s7-to-codesys @ ${esc(r.s7conv.slice(0, 8))}): объектов на входе s7conv ${r.objects_in}; bug ${r.ring.bug}, ring.lossy ${r.ring.lossy}.</p>`;
    html += table(["Вид блока", "AST совпал"], kinds);
    html += `<p>Сценарии R1 в c2s7.sim: источник ${r.source.total.scenarios_ok}/${r.source.total.scenarios}, ST′ ${r.st_prime.total.scenarios_ok}/${r.st_prime.total.scenarios} (строк ${r.st_prime.total.rows_ok}/${r.st_prime.total.rows}); stsim: ${r.stsim ? `${r.stsim.passed}/${r.stsim.total}` : "—"}.</p>`;
    const cw = e.ring_controlwin;
    html += cw ? `<p>CODESYS Control Win (R1, coUnit из s7conv gen-tests): ${cw.totals.passed}/${cw.totals.tests} тестов.</p>` : "<p>Прогон в Control Win — docs/TEST_REPORT.md.</p>";
    html += "<p class='note'>Кольцо доказывает согласованность c2s7 и s7conv, а не компиляцию в TIA: общие ошибки одного автора могут погаситься.</p>";
    return html;
  }
  const c = e.corpus;
  if (!c) return "<p>Нет данных прогона.</p>";
  const rows = (c[state.cpu] || []).map((x) => [
    `<span class="mono">${esc(x.name)}</span>`, x.lang, x.target_path,
    `${x.source.scenarios_ok}/${x.source.scenarios}`, `${x.target.scenarios_ok}/${x.target.scenarios}`,
    x.trace_source.rows ? `${x.trace_source.rows_ok}/${x.trace_source.rows}` : "—",
    x.trace_target.rows ? `${x.trace_target.rows_ok}/${x.trace_target.rows}` : "—",
  ]);
  let html = table(["POU", "Язык", "Цель", "R1 источник", "R1 выход", "R2 источник (трасса)", "R2 выход (трасса)"], rows);
  html += "<p class='note'>R1 — строка сценария = вызов; R2 — трассы CODESYS Control Win 3.5.17.30 (цикл 10 мс), c2s7.sim повторяет их по записанным отметкам времени. Блоки LAD/FBD проверены обратным чтением своего SimaticML — это самосогласованность, не независимая проверка.</p>";
  if (e.compat) html += `<p>CDS_SR/CDS_RS против Standard.SR/RS в Control Win: SR ${e.compat.sr_equal ? "совпали" : "расходятся"}, RS ${e.compat.rs_equal ? "совпали" : "расходятся"}.</p>`;
  return html;
}

function trapsTab() {
  return state.index.traps
    .map((t) => `<div class="trap"><h3>${esc(t.title)} <span class="lang">${t.verdict}</span></h3>
      <div><h2>CODESYS</h2>${pre(t.codesys)}</div><div><h2>SCL c2s7 (S7-1500)</h2>${pre(t.scl)}</div>
      <p><b>S7:</b> ${esc(t.s7_fact)}<br><span class="note">Источник: ${esc(t.s7_source)}</span></p>
      <p><b>Свидетельство:</b> ${esc(t.evidence)}<br><span class="note">Правила: ${t.rules.join(", ") || "—"}</span></p></div>`)
    .join("");
}

function renderTab() {
  const d = state.data;
  let html = "";
  if (state.tab === "equiv") html = equivTab();
  if (state.tab === "traps") html = trapsTab();
  if (state.tab === "obs")
    html = d.obs.length
      ? table(["Задача", "OB", "Номер", "Тип", "Период, мс", "Приоритет OB", "Вызовы"], d.obs.map((o) => [esc(o.task), esc(o.ob), o.number ?? "", o.kind, o.interval_ms ?? "", o.priority ?? "", esc((o.calls || []).join(", "))]))
        + "<p class='note'>Тип, номер и период OB внешний исходник не задаёт — OB создаёт инженер (roundtrip/TASKS.md).</p>"
      : "<p>Задач нет.</p>";
  if (state.tab === "tags")
    html = table(["Тег", "Таблица", "Тип", "Адрес S7", "Комментарий"], d.tags.map((t) => [`<span class="mono">${esc(t.name)}</span>`, esc(t.table), esc(t.type), `<span class="mono">${esc(t.address)}</span>`, esc(t.comment)]))
      + "<p class='note'>%IXa.b → %Ia.b (байтовая адресация битов, проба M0), %IWn → %IW(2n), %IDn → %ID(4n). Константы — лист «User constants» PLCTags.xlsx.</p>";
  if (state.tab === "probe")
    html = d.probes.length
      ? table(["Проба", "Правило", "Конструкция", "Ожидание (CODESYS)"], d.probes.map((p) => [p.id, p.rule, esc(p.construct), esc(p.expected)])) + "<p class='note'>probe/ — процедура для человека с TIA и PLCSIM; RESULTS.csv заполняется им.</p>"
      : "<p>Конструкций verify нет.</p>";
  if (state.tab === "files")
    html = `<p><a href="${d.zip}" download>Скачать tia/ (zip)</a></p>` + pre(d.files.join("\n"));
  $("tab").innerHTML = html;
}

async function load() {
  const c = state.index.cases.find((x) => x.id === state.caseId);
  state.data = await json(c.data[state.cpu]);
  renderCases();
  renderSummary();
  renderTree();
  renderPou();
  renderTab();
}

async function main() {
  state.index = await json("data/index.json");
  $("ver").textContent = state.index.tool.split(" ")[1] || "";
  document.querySelectorAll(".cpu button").forEach((b) =>
    b.addEventListener("click", () => {
      state.cpu = b.dataset.cpu;
      document.querySelectorAll(".cpu button").forEach((x) => x.classList.toggle("on", x === b));
      load();
    }),
  );
  document.querySelectorAll("#tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      state.tab = b.dataset.tab;
      document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
      renderTab();
    }),
  );
  await load();
}

main().catch((e) => { document.body.insertAdjacentHTML("beforeend", `<pre>${esc(e.message)}</pre>`); });
