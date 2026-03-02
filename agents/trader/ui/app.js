const tabs = ["Overview", "Live Event Stream", "Trace Explorer", "Decisions", "Portfolio & Execution", "Models & Learning", "Policies & Values", "System / Debug"];
let activeTab = tabs[0];
let state = { health: {}, snapshot: {}, events: [], decisions: [], executions: [], models: {}, policies: {}, logs: [], selectedCorrelationId: "" };

function $(s) { return document.querySelector(s); }
function el(tag, attrs = {}, text = "") { const n = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); if (text) n.textContent = text; return n; }

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function refreshData() {
  [state.health, state.snapshot, state.events, state.decisions, state.executions, state.models, state.policies] = await Promise.all([
    api("/api/health"),
    api("/api/state"),
    api("/api/ledger/tail?limit=500"),
    api("/api/decisions?limit=200"),
    api("/api/executions?limit=200"),
    api("/api/models"),
    api("/api/policies"),
  ]);
}

function renderTabs() {
  const nav = $("#tabs"); nav.innerHTML = "";
  tabs.forEach((tab) => {
    const b = el("button", {}, tab);
    if (tab === activeTab) b.classList.add("active");
    b.onclick = () => { activeTab = tab; render(); };
    nav.appendChild(b);
  });
}

function cardGrid(items) {
  const g = el("div", { class: "grid" });
  items.forEach(([k, v]) => {
    const c = el("div", { class: "kpi" });
    c.innerHTML = `<div>${k}</div><strong>${v ?? "-"}</strong>`;
    g.appendChild(c);
  });
  return g;
}

function table(headers, rows) {
  const t = el("table", { class: "table" });
  const h = el("tr"); headers.forEach((x) => h.appendChild(el("th", {}, x)));
  const thead = el("thead"); thead.appendChild(h); t.appendChild(thead);
  const tb = el("tbody"); rows.forEach((r) => { const tr = el("tr"); r.forEach((x) => { const td = el("td"); td.innerHTML = x; tr.appendChild(td); }); tb.appendChild(tr); });
  t.appendChild(tb);
  return t;
}

function renderStatus() {
  const m = state.snapshot.metrics || {};
  const p = state.snapshot.portfolio_state || {};
  $("#status").innerHTML = `running=${state.health.runtime_running} | mode=${m.mode || "-"} | cci_f=${(m.cci_f || 0).toFixed(3)} | equity=${p.equity || 0} | locked=${(state.snapshot.guardrails || {}).locked || false}`;
}

function renderOverview(root) {
  const m = state.snapshot.metrics || {};
  const g = state.snapshot.guardrails || {};
  const versions = {
    model: state.health.active_model_version || "none",
    policy: state.health.policy_version || "none",
    value: state.health.value_policy_version || "none",
    feature: "feature-v2",
    label: "label-v1",
  };
  root.appendChild(cardGrid([
    ["CCI-F", (m.cci_f || 0).toFixed(4)], ["Mode", m.mode], ["Equity", (state.snapshot.portfolio_state || {}).equity || 0],
    ["DD day", g.dd_day || 0], ["DD month", g.dd_month || 0], ["Trades today", g.trades_total_day || 0], ["Decisions total", state.decisions.length],
  ]));
  const versionsBox = el("pre", {}, JSON.stringify(versions, null, 2));
  root.appendChild(versionsBox);
}

function renderLiveEventStream(root) {
  const controls = el("div");
  controls.innerHTML = '<input id="flt-type" placeholder="event_type"/> <input id="flt-symbol" placeholder="symbol"/> <input id="flt-cid" placeholder="correlation_id"/> <button id="flt-apply">Filter</button>';
  root.appendChild(controls);
  let events = state.events.slice(-500);
  const rows = events.map((e) => [e.ts, e.event_type, (e.payload || {}).symbol || "-", e.correlation_id, `<button data-eid="${e.event_id}">JSON</button>`]);
  root.appendChild(table(["ts", "event_type", "symbol", "correlation_id", "raw"], rows));
  const pre = el("pre", { id: "stream-json" }, "click JSON");
  root.appendChild(pre);
  root.onclick = (ev) => {
    const btn = ev.target.closest("button[data-eid]");
    if (!btn) return;
    const item = state.events.find((x) => x.event_id === btn.dataset.eid);
    if (item) pre.textContent = JSON.stringify(item, null, 2);
  };
  controls.querySelector("#flt-apply").onclick = async () => {
    const t = controls.querySelector("#flt-type").value || "";
    const s = controls.querySelector("#flt-symbol").value || "";
    const c = controls.querySelector("#flt-cid").value || "";
    state.events = await api(`/api/ledger/query?type=${encodeURIComponent(t)}&symbol=${encodeURIComponent(s)}&correlation_id=${encodeURIComponent(c)}&limit=500`);
    render();
  };
}

async function renderTraceExplorer(root) {
  const box = el("div");
  box.innerHTML = `<input id="trace-cid" placeholder="correlation_id" value="${state.selectedCorrelationId || ""}" size="60"/> <button id="open-trace">Open Trace</button><div id="trace-body"></div>`;
  root.appendChild(box);
  box.querySelector("#open-trace").onclick = async () => {
    const cid = box.querySelector("#trace-cid").value.trim();
    if (!cid) return;
    state.selectedCorrelationId = cid;
    const trace = await api(`/api/trace/${cid}`);
    const tb = box.querySelector("#trace-body");
    tb.innerHTML = "";
    const rows = Object.entries(trace.stages).map(([k, v]) => [k, v.length, (trace.durations_by_stage_sec || {})[k.split(" ")[0]] ?? 0]);
    tb.appendChild(table(["Stage", "Events", "Duration(s)"], rows));
    tb.appendChild(el("pre", {}, JSON.stringify(trace.causality_chain, null, 2)));
  };
}

function renderDecisions(root) {
  const rows = state.decisions.map((d) => [d.ts, d.symbol, d.action, d.qty, d.p_win, d.uncertainty, d.threshold, d.mode, d.cci_f, d.model_version, `<button data-cid="${d.correlation_id}">Open Trace</button>`]);
  root.appendChild(table(["ts", "symbol", "action", "qty", "p_win", "uncertainty", "threshold", "mode", "cci_f", "model_version", "trace"], rows));
  root.onclick = (ev) => {
    const btn = ev.target.closest("button[data-cid]");
    if (!btn) return;
    state.selectedCorrelationId = btn.dataset.cid;
    activeTab = "Trace Explorer";
    render();
  };
}

function renderPortfolio(root) {
  const p = state.snapshot.portfolio_state || {};
  const positions = p.positions || {};
  root.appendChild(table(["symbol", "qty", "avg_price", "last_price", "unrealized", "realized"], Object.entries(positions).map(([s, pos]) => [s, pos.qty || 0, pos.avg_price || 0, (state.snapshot.last_prices_by_symbol || {})[s] || 0, pos.unrealized || "MOCK", p.realized_pnl || 0])));
  root.appendChild(table(["ts", "event", "symbol"], state.executions.map((x) => [x.ts, x.event_type, (x.payload || {}).symbol || "-"])));
  root.appendChild(el("div", { class: "badge mock" }, "MOCK: equity curve not implemented yet in backend"));
}

function renderModels(root) {
  root.appendChild(el("pre", {}, JSON.stringify(state.models, null, 2)));
}

function renderPolicies(root) {
  const form = el("div");
  form.innerHTML = '<input id="pwin" placeholder="p_win_threshold"/> <input id="risk" placeholder="risk_per_trade"/> <button id="set-pol">Set policy</button> <button id="set-vpol">Set value_policy MOCK</button>';
  root.appendChild(form);
  root.appendChild(el("pre", {}, JSON.stringify(state.policies, null, 2)));
  form.querySelector("#set-pol").onclick = async () => {
    await api("/api/control/set_policy", { method: "POST", body: JSON.stringify({ p_win_threshold: Number(form.querySelector("#pwin").value || 0.6), risk_per_trade: Number(form.querySelector("#risk").value || 0.005) }) });
    await refreshData(); render();
  };
  form.querySelector("#set-vpol").onclick = async () => {
    await api("/api/control/set_value_policy", { method: "POST", body: JSON.stringify({ quality_weight: 0.5, risk_weight: 0.4, note: "MOCK" }) });
    await refreshData(); render();
  };
}

function renderDebug(root) {
  root.appendChild(el("pre", {}, JSON.stringify(state.snapshot, null, 2)));
  const a1 = el("a", { href: "/api/download/ledger_tail?limit=2000", target: "_blank" }, "Download ledger tail (json)");
  root.appendChild(a1);
}

function render() {
  renderTabs(); renderStatus();
  const content = $("#content"); content.innerHTML = "";
  const panel = el("section", { class: "panel" });
  if (activeTab === "Overview") renderOverview(panel);
  if (activeTab === "Live Event Stream") renderLiveEventStream(panel);
  if (activeTab === "Trace Explorer") renderTraceExplorer(panel);
  if (activeTab === "Decisions") renderDecisions(panel);
  if (activeTab === "Portfolio & Execution") renderPortfolio(panel);
  if (activeTab === "Models & Learning") renderModels(panel);
  if (activeTab === "Policies & Values") renderPolicies(panel);
  if (activeTab === "System / Debug") renderDebug(panel);
  content.appendChild(panel);
}

async function control(action) {
  if (action === "start") {
    await api("/api/control/start", { method: "POST", body: JSON.stringify({ mode: "live", interval_sec: 1 }) });
  } else if (action === "reset_demo") {
    await api("/api/control/reset_demo", { method: "POST", body: JSON.stringify({ confirm: true }) });
  } else {
    await api(`/api/control/${action}`, { method: "POST", body: JSON.stringify({}) });
  }
  await refreshData(); render();
}

function initControls() {
  document.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.onclick = async () => { await control(btn.dataset.action); };
  });
}

function initSocket() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`);
  ws.onopen = () => ws.send(JSON.stringify({ type: "backfill", limit: 200 }));
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "event" && msg.envelope) {
        state.events.push(msg.envelope);
        if (state.events.length > 5000) state.events = state.events.slice(-5000);
        state.logs.push(`${msg.envelope.ts} ${msg.envelope.event_type}`);
        if (activeTab === "Live Event Stream") render();
      }
    } catch (e) {
      state.logs.push(String(e));
    }
  };
}

(async function bootstrap() {
  initControls();
  await refreshData();
  render();
  initSocket();
})();
