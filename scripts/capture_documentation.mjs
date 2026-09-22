/** Capture real GUI views of the bounded synthetic teaching experiment.
 * The article-regime gallery uses capture_article_examples.mjs instead.
 * No fixtures are injected into the UI and no pixels or result fields are edited.
 * Requires the built frontend, a local API serving the completed gallery workspace,
 * and the frontend lockfile's Playwright installation.
 */
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { join } from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8000" },
  manifest: { type: "string", default: "runs/documentation/gallery-manifest.json" },
  output: { type: "string", default: "runs/documentation/screenshots" },
  channel: { type: "string", default: process.platform === "darwin" ? "chrome" : "chromium" },
} });
const base = new URL(values.url);
if (!["localhost", "127.0.0.1", "[::1]"].includes(base.hostname)) {
  throw new Error("Use a locally owned documentation API.");
}
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { chromium, expect } = require("@playwright/test");
const manifest = JSON.parse(await readFile(values.manifest, "utf8"));
async function get(path) {
  const response = await fetch(new URL(`/api/v1${path}`, base));
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}
const rows = await get(`/experiments/${manifest.experiment_id}/rows`);
if (rows.length !== 6 || rows.some((row) => row.validation_status !== "valid_solution")) {
  throw new Error("Gallery requires six independently valid solved demonstrations; inspect all outcomes first.");
}
const runs = await Promise.all(rows.map((row) => get(`/runs/${row.run_id}`)));
await mkdir(values.output, { recursive: true });
const browser = await chromium.launch({ channel: values.channel, headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1280 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(String(error)));
const screenshots = [];
let currentIndex = 0;

async function open(index, tick = 0, height = 1280) {
  currentIndex = index;
  await page.setViewportSize({ width: 1920, height });
  await page.goto(new URL(`/?run=${rows[index].run_id}&tick=${tick}`, base).href);
  await expect(page.getByTestId("validation-status")).toHaveText("valid_solution");
  await expect(page.getByTestId("replay-tick")).toContainText(`t = ${tick} /`);
  await page.getByRole("button", { name: "Fit grid", exact: true }).click();
}

async function capture(file, description, extra = {}) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const pixels = await page.screenshot({ path: join(values.output, file), animations: "disabled" });
  const run = runs[currentIndex];
  const layers = await page.locator(".layer-bar label").evaluateAll((labels) => labels
    .filter((label) => label.querySelector("input")?.checked)
    .map((label) => label.textContent.trim()));
  screenshots.push({ file, description, sha256: createHash("sha256").update(pixels).digest("hex"),
    bytes: pixels.length, run_id: run.metadata.run_id,
    instance_hash: run.metadata.instance_hash, source_sha256: manifest.source_sha256,
    validation: run.result.validation.status, solver: run.metadata.effective_config.solver_id,
    setting: run.metadata.effective_config.setting, grid: [run.metadata.grid_width, run.metadata.grid_height],
    agents: run.metadata.agent_count, tick_label: await page.getByTestId("replay-tick").textContent(),
    viewport: page.viewportSize(), layers, ...extra });
}

try {
  await open(0, 1);
  await page.getByLabel("Recorded reservations", { exact: true }).check();
  await capture("crossings-32-80.png", "Eighty HeatMap agents in forty constructed local crossing pairs; executed paths and reservations.");

  await open(1, 10);
  await page.getByLabel("Executed paths", { exact: true }).uncheck();
  await capture("warehouse-32-80.png", "Eighty agents in synthetic warehouse aisles; positions and goals without path clutter.");
  await page.getByRole("button", { name: "agent_0", exact: true }).click();
  await page.getByLabel("Executed paths", { exact: true }).check();
  await capture("warehouse-selected-agent.png", "One selected executed route; other trajectories are dimmed for inspection.", { selected_agent: "agent_0" });

  await open(2, 10, 1580);
  await page.getByLabel("Executed paths", { exact: true }).uncheck();
  await capture("warehouse-64-100.png", "The GUI request limits: 64 by 64 cells and one hundred agents on a synthetic aisle map.");

  const candidate = runs[3].result.frames.flatMap((frame) => (frame.local_heat || [])
    .filter((record) => record.status === "recorded" && Object.keys(record.aggregate || {}).length > 0)
    .map((record) => ({ frame, record })))
    .sort((a, b) => Object.keys(b.record.aggregate).length - Object.keys(a.record.aggregate).length)[0];
  if (!candidate) throw new Error("No recorded nonzero HeatMap decision is available.");
  await open(3, candidate.frame.tick, 1420);
  await page.getByRole("button", { name: candidate.record.agent_id, exact: true }).click();
  await page.getByLabel("FoV geometry", { exact: true }).check();
  await page.getByLabel("Recorded local heat", { exact: true }).check();
  await page.getByLabel("Recorded heat decision", { exact: true }).selectOption(candidate.record.record_id);
  await capture("recorded-local-heat.png", "Actual pre-move HeatMap weights, shown beside the following post-move frame; no hindsight weights substituted.",
    { selected_agent: candidate.record.agent_id, heat_record_id: candidate.record.record_id, decision_tick: candidate.record.tick });

  await page.getByLabel("Recorded local heat", { exact: true }).uncheck();
  await page.getByLabel("Recorded local view", { exact: true }).check();
  await capture("recorded-local-view.png", "The selected agent's recorded observation, delivered message paths and known static map.",
    { selected_agent: candidate.record.agent_id });

  const promise = runs[3].result.frames.flatMap((frame) => Object.entries(frame.commitments || {})
    .filter(([, records]) => records.some((record) => record.start_tick + record.points.length - 1 >= frame.tick))
    .map(([agent, records]) => ({ frame, agent, count: records.length })))
    .sort((a, b) => b.count - a.count)[0];
  if (!promise) throw new Error("No live recorded reservation is available.");
  await open(3, promise.frame.tick);
  await page.getByRole("button", { name: promise.agent, exact: true }).click();
  await page.getByLabel("Executed paths", { exact: true }).uncheck();
  await page.getByLabel("Recorded reservations", { exact: true }).check();
  await page.getByLabel("FoV geometry", { exact: true }).check();
  await capture("recorded-commitments.png", "Live reservations owned by the selected agent, with absolute ticks and its FoV geometry.", { selected_agent: promise.agent });

  await open(3, 0, 1420);
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByRole("combobox", { name: /^Left run/ }).selectOption(rows[3].run_id);
  await page.getByRole("combobox", { name: /^Right run/ }).selectOption(rows[4].run_id);
  await page.getByRole("button", { name: "Build matched cohort", exact: true }).click();
  await expect(page.getByText("Paired: 1 · Common solved: 1", { exact: false })).toBeVisible();
  await page.getByRole("slider", { name: "Replay tick", exact: true }).fill("6");
  await expect(page.getByTestId("replay-tick")).toContainText("t = 6 /");
  await capture("paired-replay.png", "HeatMap and PathAware on the same eight-agent scenario at t=6; one descriptive common-solved pair.",
    { right_run_id: rows[4].run_id, treatment: ["solver_id"], common_solved: 1 });

  if (browserErrors.length) throw new Error(browserErrors.join("\n"));
  const sourceFiles = [
    "scripts/documentation_examples.py", "scripts/capture_documentation.mjs",
    "frontend/package-lock.json", "frontend/src/App.tsx", "frontend/src/index.css",
    "frontend/src/components/GridViewport.tsx", "frontend/src/components/agentColors.ts",
  ];
  const recipeHashes = Object.fromEntries(await Promise.all(sourceFiles.map(async (file) => [
    file, createHash("sha256").update(await readFile(new URL(`../${file}`, import.meta.url))).digest("hex"),
  ])));
  const receipt = {
    schema_version: "documentation-gallery-1", captured_at: new Date().toISOString(),
    purpose: "Synthetic software illustrations, not article benchmark or performance evidence",
    method: "Unmodified browser screenshots of the real local application; ordinary UI controls only",
    experiment_id: manifest.experiment_id, source_sha256: manifest.source_sha256,
    git_commit: manifest.provenance.git_commit, browser: browser.version(), screenshots,
    recipe_and_view_hashes: recipeHashes,
    all_trials: rows.map((row, index) => ({ trial_id: row.trial_id, run_id: row.run_id,
      scenario: runs[index].metadata.instance.name, validation_status: row.validation_status,
      state: row.state, solver_id: row.solver_id, effective_config: runs[index].metadata.effective_config })),
  };
  await writeFile(join(values.output, "provenance.json"), JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify({ screenshots: screenshots.length, total_bytes: screenshots.reduce((n, s) => n + s.bytes, 0), browser_errors: browserErrors }));
} finally {
  await browser.close();
}
