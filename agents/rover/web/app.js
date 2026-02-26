const canvas = document.getElementById("sim");
const ctx = canvas.getContext("2d");
const logsEl = document.getElementById("logs");
const metricsEl = document.getElementById("metrics");

let world = null;
let obstacles = [];
let lastAction = { type: "robot.stop" };

const apiBase = `${window.location.pathname.replace(/\/$/, "")}`;
const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${apiBase}/ws`;
const ws = new WebSocket(wsUrl);

function draw() {
  if (!world) return;
  const tileW = canvas.width / world.w;
  const tileH = canvas.height / world.h;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#6b7280";
  obstacles.forEach((o) => {
    ctx.fillRect(o.x * tileW, o.y * tileH, tileW, tileH);
  });
  ctx.fillStyle = "#16a34a";
  ctx.fillRect(world.goal.x * tileW, world.goal.y * tileH, tileW, tileH);
  ctx.fillStyle = "#2563eb";
  ctx.fillRect(world.robot.x * tileW, world.robot.y * tileH, tileW, tileH);
}

function appendLog(entry) {
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = `[${entry.ts}] ${entry.level.toUpperCase()} ${entry.component} ${entry.message} ${JSON.stringify(entry.data || {})}`;
  logsEl.appendChild(line);
  logsEl.scrollTop = logsEl.scrollHeight;
}

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "init") {
    obstacles = data.world.obstacles || [];
    world = { ...data.world };
    (data.logs || []).forEach(appendLog);
    draw();
  } else if (data.type === "frame") {
    world = data.world;
    lastAction = data.last_action || lastAction;
    metricsEl.textContent = JSON.stringify({
      tick: data.tick,
      episode_id: data.episode_id,
      reward: data.metrics.reward,
      avg_reward_window: data.metrics.avg_reward_window,
      distance: data.metrics.distance,
      collisions: data.metrics.collisions,
      action: lastAction,
      running: data.metrics.running,
      done: data.metrics.done,
      reason: data.metrics.reason,
    }, null, 2);
    draw();
  } else if (data.type === "log") {
    appendLog(data);
  }
};

async function post(path) {
  await fetch(`${apiBase}/control/${path}`, { method: "POST" });
}

document.getElementById("start").onclick = () => post("start");
document.getElementById("stop").onclick = () => post("stop");
document.getElementById("reset").onclick = () => post("reset");
