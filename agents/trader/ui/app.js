const tabs = ["Overview", "Market & Regime", "Decisions", "Execution / Portfolio", "Models & Learning", "System / Logs"];
let activeTab = tabs[0];
let state = { decisions: [], trades: [], logs: [], models: {}, portfolio: {}, snapshot: {} };

function $(sel) { return document.querySelector(sel); }
function el(tag, attrs = {}, text = "") { const n = document.createElement(tag); Object.entries(attrs).forEach(([k,v]) => n.setAttribute(k,v)); if (text) n.textContent = text; return n; }

function renderTabs() {
  const nav = $("#tabs"); nav.innerHTML = "";
  tabs.forEach(tab => {
    const b = el("button", {}, tab);
    if (tab === activeTab) b.classList.add("active");
    b.onclick = () => { activeTab = tab; render(); };
    nav.appendChild(b);
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function refreshData() {
  state.snapshot = await api("/api/state");
  state.decisions = await api("/api/decisions?limit=100");
  state.trades = await api("/api/trades?limit=100");
  state.portfolio = await api("/api/portfolio");
  state.models = await api("/api/models");
}

function cardGrid(items) {
  const g = el("div", { class: "grid" });
  items.forEach(([k,v]) => {
    const c = el("div", { class: "kpi" });
    c.innerHTML = `<div>${k}</div><strong>${v}</strong>`;
    g.appendChild(c);
  });
  return g;
}

function renderOverview(root) {
  const m = state.snapshot.metrics || {};
  const p = state.snapshot.portfolio_state || {};
  if (m.mode === "locked" || !(state.snapshot.data_quality || {}).integrity_ok) {
    root.appendChild(el("div", { class: "alert" }, "Alert: runtime locked or data integrity issues detected"));
  }
  root.appendChild(cardGrid([
    ["CCI-F", (m.cci_f || 0).toFixed(3)], ["Mode", m.mode || "-"], ["Equity", p.equity || 0],
    ["DD Day", state.snapshot.dd_day || 0], ["DD Month", state.snapshot.dd_month || 0],
    ["Trades", m.trades_executed || 0], ["Decisions", m.decisions_total || 0]
  ]));
}

function table(headers, rows) {
  const t = el("table", { class: "table" });
  const thead = el("thead"); const tr = el("tr"); headers.forEach(h => tr.appendChild(el("th", {}, h))); thead.appendChild(tr); t.appendChild(thead);
  const tb = el("tbody");
  rows.forEach(r => { const rr = el("tr"); r.forEach(v => { const td = el("td"); td.innerHTML = v; rr.appendChild(td); }); tb.appendChild(rr); });
  t.appendChild(tb); return t;
}

function renderMarket(root) {
  const market = state.snapshot.market_state || {};
  const rows = [];
  Object.entries(market).forEach(([symbol, tfData]) => {
    ["1h","4h"].forEach(tf => {
      const d = (tfData || {})[tf] || {}; const f = d.features || {};
      rows.push([symbol, tf, f.last_close || "-", d.regime || "-", f.atr || "-", f.rsi || "-", f.ema_slope || "-", f.bb_width || "-", f.adx_like || "-"]);
    });
  });
  root.appendChild(table(["Symbol","TF","Last Close","Regime","ATR","RSI","EMA slope","BB width","ADX-like"], rows));
  root.appendChild(el("p", { class: "badge mock" }, "Mock-friendly view: mini chart omitted in v0"));
}

function renderDecisions(root) {
  const rows = state.decisions.map(d => [d.timestamp || "-", d.symbol || "-", d.action || "-", d.p_win ?? "-", `<button data-id="${d.decision_id}">details</button>`]);
  root.appendChild(table(["Time","Symbol","Action","p_win","Details"], rows));
  root.onclick = (ev) => {
    const btn = ev.target.closest("button[data-id]");
    if (!btn) return;
    const item = state.decisions.find(d => d.decision_id === btn.dataset.id);
    alert(JSON.stringify(item, null, 2));
  };
}

function renderExecution(root) {
  const positions = state.portfolio.positions || {};
  const pRows = Object.entries(positions).map(([s,p]) => [s, p.qty || 0, p.avg_price || 0, (p.qty || 0) * (p.avg_price || 0)]);
  root.appendChild(table(["Symbol","Qty","Avg Price","Exposure"], pRows));
  const tRows = state.trades.map(t => [t.timestamp || "-", t.symbol || "-", t.side || "-", t.qty || 0, t.price || 0, t.pnl || 0]);
  root.appendChild(table(["Time","Symbol","Side","Qty","Price","PnL"], tRows));
  root.appendChild(el("p", { class: "badge mock" }, "Equity curve currently mock-backed."));
}

function renderModels(root) {
  const m = state.models || {};
  root.appendChild(cardGrid([["Active Model", m.active_model_version || "none"], ["Train State", (m.last_train_run || {}).state || "none"]]));
  const rows = (m.model_registry || []).map(i => [i.version || "-", i.status || "-", i.score || "-", i.created_at || "-"]);
  root.appendChild(table(["Version","Status","Score","Created"], rows));
  const box = el("div");
  box.innerHTML = '<input id="csv-path" placeholder="agents/trader/data/sample_features.csv" size="48"/><button id="btn-train">Train</button><pre id="train-status"></pre>';
  root.appendChild(box);
  box.querySelector("#btn-train").onclick = async () => {
    const csv = box.querySelector("#csv-path").value || undefined;
    const out = await api("/api/train", { method: "POST", body: JSON.stringify({ mode: "from_features", csv_path: csv }) });
    box.querySelector("#train-status").textContent = `accepted: ${out.run_id}`;
  };
}

function renderLogs(root) {
  const wrap = el("div");
  wrap.innerHTML = '<button id="download-decisions">Download decisions</button> <button id="download-state">Download state</button>';
  root.appendChild(wrap);
  const pre = el("pre", {}, state.logs.slice(-100).join("\n"));
  root.appendChild(pre);
  wrap.querySelector("#download-decisions").onclick = () => window.open('/api/download/decisions', '_blank');
  wrap.querySelector("#download-state").onclick = () => window.open('/api/download/state', '_blank');
}

function render() {
  renderTabs();
  const content = $("#content"); content.innerHTML = "";
  const panel = el("section", { class: "panel" });
  if (activeTab === "Overview") renderOverview(panel);
  if (activeTab === "Market & Regime") renderMarket(panel);
  if (activeTab === "Decisions") renderDecisions(panel);
  if (activeTab === "Execution / Portfolio") renderExecution(panel);
  if (activeTab === "Models & Learning") renderModels(panel);
  if (activeTab === "System / Logs") renderLogs(panel);
  content.appendChild(panel);
}

async function control(action, body = {}) {
  await api(`/api/control/${action}`, { method: "POST", body: JSON.stringify(body) });
  await refreshData(); render();
}

function initControls() {
  document.querySelectorAll("button[data-action]").forEach(btn => {
    btn.onclick = async () => {
      const action = btn.dataset.action;
      if (action === "train") {
        activeTab = "Models & Learning"; render(); return;
      }
      await control(action, action === "reset" ? { confirm: true } : {});
    };
  });
}

function initSocket() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/events`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      state.logs.push(`${msg.ts} [${msg.type}] ${JSON.stringify(msg.payload)}`);
      if (msg.type === "metrics") state.snapshot.metrics = msg.payload;
      if (["decision", "execution", "candle"].includes(msg.type)) refreshData().then(render);
      if (activeTab === "System / Logs") render();
    } catch (_) {}
  };
}

(async function bootstrap() {
  initControls();
  await refreshData();
  render();
  initSocket();
})();
