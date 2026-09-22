import { Application, Graphics } from "pixi.js";
const size = 10,
  n = 32,
  count = 80,
  iterations = 120;
const fixture = Array.from({ length: count }, (_, i) => ({
  id: i,
  x: i % 32,
  y: Math.floor(i / 32),
}));
const obstacles = Array.from({ length: 60 }, (_, i) => [
  (i % 20) + 5,
  Math.floor(i / 20) + 15,
]);
function stats(values: number[]) {
  const measured = values.slice(10);
  const ordered = [...measured].sort((a, b) => a - b);
  return {
    median_ms: ordered[Math.floor(measured.length * 0.5)],
    p95_ms: ordered[Math.floor(measured.length * 0.95)],
    iterations: measured.length,
    warmup_frames_excluded: 10,
  };
}
async function run() {
  const c = document.createElement("canvas");
  c.width = n * size;
  c.height = n * size;
  document.querySelector("#canvas")!.append(c);
  const ctx = c.getContext("2d")!;
  const timings: number[] = [];
  for (let t = 0; t < iterations; t++) {
    const start = performance.now();
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.strokeStyle = "#334155";
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++)
        ctx.strokeRect(x * size, y * size, size, size);
    ctx.fillStyle = "#64748b";
    for (const [x, y] of obstacles)
      ctx.fillRect(x * size, y * size, size, size);
    ctx.fillStyle = "#06b6d4";
    for (const a of fixture) {
      ctx.beginPath();
      ctx.arc(
        (((a.x + t) % n) + 0.5) * size,
        (a.y + 0.5) * size,
        3,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }
    timings.push(performance.now() - start);
    if (t % 10 === 0) await new Promise(requestAnimationFrame);
  }
  const app = new Application();
  const gpu: number[] = [];
  let pixiError: string | null = null;
  try {
    await app.init({ width: n * size, height: n * size, autoStart: false });
    document.querySelector("#pixi")!.append(app.canvas);
    const g = new Graphics();
    app.stage.addChild(g);
    for (let t = 0; t < iterations; t++) {
      const start = performance.now();
      g.clear();
      for (let y = 0; y < n; y++)
        for (let x = 0; x < n; x++)
          g.rect(x * size, y * size, size, size).stroke({
            color: 0x334155,
            width: 1,
          });
      for (const [x, y] of obstacles)
        g.rect(x * size, y * size, size, size).fill(0x64748b);
      for (const a of fixture)
        g.circle((((a.x + t) % n) + 0.5) * size, (a.y + 0.5) * size, 3).fill(
          0x06b6d4,
        );
      app.render();
      gpu.push(performance.now() - start);
      if (t % 10 === 0) await new Promise(requestAnimationFrame);
    }
  } catch (e) {
    pixiError = String(e);
  }
  const receipt = {
    fixture: {
      grid: [n, n],
      agents: count,
      obstacles: obstacles.length,
      final_tick: iterations - 1,
      final_agent_0: [(iterations - 1) % n, 0],
    },
    canvas: stats(timings),
    pixi: gpu.length ? stats(gpu) : null,
    pixi_error: pixiError,
    user_agent: navigator.userAgent,
    scope:
      "Local headless browser CPU submission times; not GPU completion or general scale guarantees",
  };
  document.querySelector("#receipt")!.textContent = JSON.stringify(
    receipt,
    null,
    2,
  );
}
run();
