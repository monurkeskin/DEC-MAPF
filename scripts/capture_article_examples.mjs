/** Capture real alpha GUI views of two independently checked article-regime replays.
 * Input is a diagnostic parity receipt. Output excludes local source paths.
 * No data injection, synthesized observations or screenshot compositing is used.
 */
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { join } from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8001" },
  selection: { type: "string" },
  output: { type: "string", default: "runs/article-gallery" },
  channel: { type: "string", default: process.platform === "darwin" ? "chrome" : "chromium" },
} });
if (!values.selection) throw new Error("Provide --selection PATH to the diagnostic parity receipt.");
const base = new URL(values.url);
if (!["localhost", "127.0.0.1", "[::1]"].includes(base.hostname)) throw new Error("Use a locally owned GUI.");
const selection = JSON.parse(await readFile(values.selection, "utf8"));
if (selection.status !== "passed" || selection.runs.length !== 2 || selection.runs.some(r => !r.paths_and_scientific_metrics_identical)) {
  throw new Error("Both original-solution / full-trace parity checks must pass first.");
}
async function get(path) {
  const response = await fetch(new URL(`/api/v1${path}`, base));
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}
const runs = await Promise.all(selection.runs.map(r => get(`/runs/${r.diagnostic_run_id}`)));
for (const [index, run] of runs.entries()) {
  if (run.result.validation.status !== "valid_solution" || !run.result.success || run.metadata.agent_count !== 80 ||
      run.metadata.provenance.source_sha256 !== selection.runs[index].original_source_sha256) {
    throw new Error("Run differs from selected validated diagnostic evidence.");
  }
}
const require = createRequire(new URL("../frontend/package.json", import.meta.url));
const { chromium, expect } = require("@playwright/test");
await mkdir(values.output, { recursive: true });
const browser = await chromium.launch({ channel: values.channel, headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1280 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", error => errors.push(String(error)));
const screenshots = [];
let current = 0;
async function open(index, tick) {
  current = index;
  await page.goto(new URL(`/?run=${runs[index].metadata.run_id}&tick=${tick}`, base).href);
  await expect(page.getByTestId("validation-status")).toHaveText("valid_solution", {timeout: 20000});
  await expect(page.getByTestId("replay-tick")).toContainText(`t = ${tick} /`, {timeout: 20000});
  await expect(page.locator("header strong")).toHaveText("DEC-MAPF");
  await expect(page.getByRole("heading", {name: `Agents · t=${tick}`, exact: true})).toBeVisible({timeout: 45000});
  await expect(page.getByText("Loading replay frames…", {exact: true})).toHaveCount(0, {timeout: 45000});
  await page.getByLabel("Executed paths", {exact: true}).uncheck();
  await page.getByRole("button", {name: "Fit grid", exact: true}).click();
}
async function capture(file, description, extra = {}) {
  await expect(page.getByText("Loading replay frames…", {exact: true})).toHaveCount(0, {timeout: 45000});
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const pixels = await page.screenshot({path: join(values.output,file), animations: "disabled"});
  const run = runs[current], meta = run.metadata, instance = meta.instance;
  const layers = await page.locator(".layer-bar label").evaluateAll(labels => labels
    .filter(label => label.querySelector("input")?.checked).map(label => label.textContent.trim()));
  const cellCount = meta.grid_width * meta.grid_height;
  screenshots.push({file, description, sha256: createHash("sha256").update(pixels).digest("hex"), bytes: pixels.length,
    run_id: meta.run_id, original_run_id: selection.runs[current].original_run_id,
    instance_hash: meta.instance_hash, source_sha256: meta.provenance.source_sha256,
    validation: run.result.validation.status, solver: meta.effective_config.solver_id,
    setting: meta.effective_config.setting, commitment: meta.effective_config.commitment_type,
    fov: meta.effective_config.fov_size, grid: [meta.grid_width,meta.grid_height], agents: meta.agent_count,
    obstacles: instance.obstacles.length, obstacle_fraction: instance.obstacles.length/cellCount,
    initial_agent_fraction_of_free_cells: meta.agent_count/(cellCount-instance.obstacles.length),
    rendered_frame_label: await page.getByRole("heading", {name: /^Agents · t=/}).textContent(),
    tick_label: await page.getByTestId("replay-tick").textContent(), viewport: page.viewportSize(),layers,...extra});
}
try {
  await open(0, 1);
  await capture("article-16-80-overview.png", "A solved 16x16 article-regime instance with 80 HeatMap agents; 31.25% initial occupancy, SC and FoV5.");
  await open(1, 1);
  await capture("article-32-20-80-overview.png", "A solved 32x32 article-regime instance with 205 blocked cells and 80 HeatMap agents, ZC and FoV5.");
  const heat = runs[0].result.frames.filter(frame => frame.tick > 0 && frame.tick <= 5)
    .flatMap(frame => (frame.local_heat || []).filter(record => record.status === "recorded" && Object.keys(record.aggregate || {}).length)
      .map(record => ({frame,record})))
    .sort((a,b) => Object.keys(b.record.aggregate).length - Object.keys(a.record.aggregate).length)[0];
  if (!heat) throw new Error("No recorded early decision heat; do not invent a diagnostic layer.");
  await open(0, heat.frame.tick);
  await page.getByRole("button", {name: heat.record.agent_id,exact: true}).click();
  await page.getByLabel("FoV geometry", {exact: true}).check();
  await page.getByLabel("Recorded local heat", {exact: true}).check();
  await page.getByLabel("Recorded heat decision", {exact: true}).selectOption(heat.record.record_id);
  await capture("article-16-local-heat.png", "Actual recorded HeatMap weights for one early decision; no occupancy proxy or hindsight weights.",
    {selected_agent: heat.record.agent_id, heat_record_id: heat.record.record_id, decision_tick: heat.record.tick});
  await page.getByLabel("Recorded local heat", {exact: true}).uncheck();
  await page.getByLabel("Recorded local view", {exact: true}).check();
  await capture("article-16-local-view.png", "Recipient-local recorded information during the same decision; unavailable global agents remain hidden.", {selected_agent: heat.record.agent_id});
  const commitment = runs[0].result.frames.filter(frame => frame.tick > 0 && frame.tick <= 5)
    .flatMap(frame => Object.entries(frame.commitments || {}).filter(([,records]) => records.some(r => r.start_tick+r.points.length-1 >= frame.tick))
      .map(([agent,records]) => ({frame,agent,count: records.length})))
    .sort((a,b) => b.count-a.count)[0];
  if (!commitment) throw new Error("No live recorded commitment is available.");
  await open(0, commitment.frame.tick);
  await page.getByRole("button", {name: commitment.agent,exact: true}).click();
  await page.getByLabel("Recorded reservations", {exact: true}).check();
  await page.getByLabel("FoV geometry", {exact: true}).check();
  await capture("article-16-commitments.png", "The selected owner's recorded finite commitments in the dense 16x16 instance.", {selected_agent: commitment.agent});
  await open(1, 1);
  const selectedAgent = runs[1].metadata.instance.agent_order[0];
  await page.getByRole("button", {name: selectedAgent,exact: true}).click();
  await page.getByLabel("Executed paths", {exact: true}).check();
  await capture("article-32-selected-route.png", "One executed route through the 20% obstacle regime; trajectory includes hindsight and does not claim agent foreknowledge.", {selected_agent: selectedAgent});
  if (errors.length) throw new Error(errors.join("\n"));
  const all_trials = runs.map((run,index) => ({
    original_run_id: selection.runs[index].original_run_id, original_trial_id: selection.runs[index].original_trial_id,
    original_controller: selection.runs[index].original_controller, original_artifact_sha256: selection.runs[index].original_artifact_sha256,
    original_source_sha256: selection.runs[index].original_source_sha256,
    run_id: run.metadata.run_id, scenario: run.metadata.instance.name,
    source_sha256: run.metadata.provenance.source_sha256, validation_status: run.result.validation.status,
    solver_id: run.metadata.effective_config.solver_id, effective_config: run.metadata.effective_config,
    paths_and_scientific_metrics_identical: true, recording_change: "metrics-only to full-trace; no new scientific replicate",
    makespan: run.result.makespan, sum_of_costs: run.result.sum_of_costs, negotiations: run.result.negotiation_count,
  }));
  const recipe = ["scripts/capture_article_examples.mjs","frontend/src/App.tsx","frontend/src/components/GridViewport.tsx","frontend/package-lock.json"];
  const recipe_and_view_hashes = Object.fromEntries(await Promise.all(recipe.map(async file => [file,createHash("sha256").update(await readFile(new URL(`../${file}`,import.meta.url))).digest("hex")])));
  await writeFile(join(values.output,"provenance.json"),JSON.stringify({
    schema_version: "article-regime-gallery-1", captured_at: new Date().toISOString(),
    display_name: "DEC-MAPF", stage: "alpha research software",
    purpose: "Selected solved modern executions from article-regime scenario populations; not a scaling benchmark or full reproduction claim",
    method: "Unmodified real GUI screenshots; paths and canonical metrics checked against original metrics-only outcomes before capture",
    selection: "HeatMap Setting 4 FoV5; first scenario name/trial ID among solved 16x16 SC and 32x32/205-obstacle ZC cases; views chosen to explain density and early local decisions",
    browser: browser.version(),screenshots,all_trials,recipe_and_view_hashes,
  },null,2)+"\n");
  console.log(JSON.stringify({screenshots:screenshots.length,browser_errors:errors,total_bytes:screenshots.reduce((n,s)=>n+s.bytes,0)}));
} finally { await browser.close(); }
