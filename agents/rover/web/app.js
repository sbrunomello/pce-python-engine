const canvas = document.getElementById("sim");
const ctx = canvas.getContext("2d");
const logsEl = document.getElementById("logs");
const metricsEl = document.getElementById("metrics");
const metricsRawEl = document.getElementById("metricsRaw");
const statusBadge = document.getElementById("statusBadge");
const autoScrollEl = document.getElementById("autoScroll");

let world = null;
let obstacles = [];
let lastAction = { type: "robot.stop" };
let latestTick = -1;
let runtimeElapsedSeconds = 0;

const MAX_LOG_LINES = 500;
const apiBase = `${window.location.pathname.replace(/\/$/, "")}`;
const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${apiBase}/ws`;
const ws = new WebSocket(wsUrl);

function directionTriangle(robot, tileW, tileH) {
  const cx = robot.x * tileW + tileW / 2;
  const cy = robot.y * tileH + tileH / 2;
  const r = Math.min(tileW, tileH) * 0.44;
  const angles = {
    0: -Math.PI / 2,
    1: 0,
    2: Math.PI / 2,
    3: Math.PI,
  };
  const a = angles[robot.dir] ?? 0;
  return [
    [cx + Math.cos(a) * r, cy + Math.sin(a) * r],
    [cx + Math.cos(a + 2.5) * r * 0.7, cy + Math.sin(a + 2.5) * r * 0.7],
    [cx + Math.cos(a - 2.5) * r * 0.7, cy + Math.sin(a - 2.5) * r * 0.7],
  ];
}

function drawGrid(tileW, tileH, w, h) {
  ctx.strokeStyle = "#1f3355";
  ctx.lineWidth = 1;
  for (let x = 0; x <= w; x += 1) {
    ctx.beginPath();
    ctx.moveTo(x * tileW, 0);
    ctx.lineTo(x * tileW, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y <= h; y += 1) {
    ctx.beginPath();
    ctx.moveTo(0, y * tileH);
    ctx.lineTo(canvas.width, y * tileH);
    ctx.stroke();
  }
}

function draw() {
  if (!world) return;
  const tileW = canvas.width / world.w;
  const tileH = canvas.height / world.h;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  drawGrid(tileW, tileH, world.w, world.h);

  ctx.fillStyle = "#64748b";
  obstacles.forEach((o) => {
    ctx.fillRect(o.x * tileW, o.y * tileH, tileW, tileH);
  });

  ctx.fillStyle = "#16a34a";
  ctx.fillRect(world.goal.x * tileW, world.goal.y * tileH, tileW, tileH);
  ctx.strokeStyle = "#bbf7d0";
  ctx.strokeRect(world.goal.x * tileW + 1, world.goal.y * tileH + 1, Math.max(1, tileW - 2), Math.max(1, tileH - 2));

  const triangle = directionTriangle(world.robot, tileW, tileH);

  if (world.start) {
    ctx.fillStyle = "#f97316";
    ctx.fillRect(world.start.x * tileW, world.start.y * tileH, tileW, tileH);
    ctx.strokeStyle = "#fdba74";
    ctx.strokeRect(
      world.start.x * tileW + 1,
      world.start.y * tileH + 1,
      Math.max(1, tileW - 2),
      Math.max(1, tileH - 2),
    );
  }

  ctx.fillStyle = "#ef4444";
  ctx.beginPath();
  ctx.moveTo(triangle[0][0], triangle[0][1]);
  ctx.lineTo(triangle[1][0], triangle[1][1]);
  ctx.lineTo(triangle[2][0], triangle[2][1]);
  ctx.closePath();
  ctx.fill();
}

function metricRow(label, value) {
  return `<dt>${label}</dt><dd>${value}</dd>`;
}

function updateMetrics(data) {
  const metrics = data.metrics || {};
  const running = Boolean(metrics.running);
  const done = Boolean(metrics.done);
  const status = done ? "DONE" : (running ? "RUNNING" : "STOPPED");

  statusBadge.textContent = status;
  statusBadge.className = `badge ${done ? "done" : (running ? "running" : "stopped")}`;

  runtimeElapsedSeconds = Number(metrics.elapsed_seconds || data?.runtime?.elapsed_seconds || runtimeElapsedSeconds || 0);

  metricsEl.innerHTML = [
    metricRow("Tick", data.tick ?? "-"),
    metricRow("Episode", data.episode_id ?? "-"),
    metricRow("Reward", Number(metrics.reward || 0).toFixed(2)),
    metricRow("Avg Reward (window)", Number(metrics.avg_reward_window || 0).toFixed(2)),
    metricRow("Distance", metrics.distance ?? "-"),
    metricRow("Collisions", metrics.collisions ?? "-"),
    metricRow("Battery", Number(data?.world?.robot?.energy || 0).toFixed(1)),
    metricRow("Attempts Total", metrics.attempts_total ?? 0),
    metricRow("Successes", metrics.successes ?? 0),
    metricRow("Fail Battery", metrics.failures_battery ?? 0),
    metricRow("Fail Timeout", metrics.failures_timeout ?? 0),
    metricRow("Fail Collision", metrics.failures_collision ?? 0),
    metricRow("Success Rate", `${(Number(metrics.success_rate || 0) * 100).toFixed(1)}%`),
    metricRow("Run Timer (s)", runtimeElapsedSeconds.toFixed(1)),
    metricRow("Last Action", lastAction.type || "robot.stop"),
    metricRow("Epsilon", metrics.epsilon !== null && metrics.epsilon !== undefined ? Number(metrics.epsilon).toFixed(4) : "-"),
    metricRow("Policy Mode", metrics.policy_mode || "-"),
    metricRow("Best Action", metrics.best_action || "-"),
    metricRow("Done", done ? "yes" : "no"),
    metricRow("Reason", metrics.reason || "-"),
  ].join("");

  metricsRawEl.textContent = JSON.stringify(data, null, 2);
}

function appendLog(entry) {
  const line = document.createElement("div");
  const level = (entry.level || "info").toLowerCase();
  line.className = `log-line ${level}`;
  line.textContent = `[${entry.ts}] ${level.toUpperCase()} ${entry.component} ${entry.message} ${JSON.stringify(entry.data || {})}`;
  logsEl.appendChild(line);

  while (logsEl.childElementCount > MAX_LOG_LINES) {
    logsEl.removeChild(logsEl.firstChild);
  }

  if (autoScrollEl.checked) {
    logsEl.scrollTop = logsEl.scrollHeight;
  }
}

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "init") {
    obstacles = data.world.obstacles || [];
    world = { ...data.world };
    latestTick = Math.max(latestTick, data.tick || 0);
    (data.logs || []).forEach(appendLog);
    draw();
    return;
  }

  if (data.type === "frame") {
    // Ignore out-of-order frames to keep HUD and canvas consistent.
    if (typeof data.tick === "number" && data.tick < latestTick) {
      return;
    }
    latestTick = data.tick;
    world = data.world || world;
    lastAction = data.last_action || lastAction;
    updateMetrics(data);
    draw();
    return;
  }

  if (data.type === "log") {
    appendLog(data);
  }
};

async function post(path) {
  await fetch(`${apiBase}/control/${path}`, { method: "POST" });
}

document.getElementById("start").onclick = () => post("start");
document.getElementById("stop").onclick = () => post("stop");
document.getElementById("reset").onclick = () => post("reset");
document.getElementById("resetStats").onclick = () => post("reset_stats");
document.getElementById("clearLogs").onclick = () => { logsEl.innerHTML = ""; };
document.getElementById("toggleRaw").onclick = () => {
  metricsRawEl.classList.toggle("hidden");
};
