import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
import type { DecisionHeatRecord, FrameSnapshot } from "../src/api/types";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("mapf-advanced", "true"));
});

test("TAOP v2 and the alternative protocol produce distinct preview identities", async ({
  page,
}) => {
  await page.goto("/");
  const protocol = page.getByRole("combobox", {
    name: /^Negotiation protocol/,
  });
  await expect(protocol).toHaveValue("taop-v2");
  const identities: string[] = [];
  for (const value of ["taop-v2", "taop-v1"]) {
    await protocol.selectOption(value);
    const preview = page.waitForResponse((r) =>
      r.url().endsWith("/plans/preview"),
    );
    await page
      .getByRole("button", { name: "Preview effective inputs" })
      .click();
    const body = await (await preview).json();
    expect(body.plans[0].effective_config.negotiation_protocol).toBe(value);
    identities.push(body.plans[0].definition_digest);
  }
  expect(identities[0]).not.toBe(identities[1]);
});

test("a real stalled negotiation retains readable diagnostics after reload", async ({
  page,
}) => {
  const response = await page.request.post("/api/v1/jobs", {
    data: {
      grid_width: 3,
      grid_height: 1,
      starts: { a: [0, 0], b: [2, 0] },
      goals: { a: [2, 0], b: [0, 0] },
      solver_id: "Decentralized-Greedy",
      setting: "SETTING_3",
      initial_tokens: 0,
      fov_size: 5,
      timeout_sec: null,
      negotiation_deadline_sec: 0.05,
    },
  });
  expect(response.status()).toBe(202);
  const { job_id } = await response.json();
  await expect
    .poll(async () => {
      const job = await (
        await page.request.get(`/api/v1/jobs/${job_id}`)
      ).json();
      return ["completed", "timed_out"].includes(job.state);
    })
    .toBe(true);
  await page.goto("/");
  await page.evaluate((id) => localStorage.setItem("mapf-job", id), job_id);
  await page.reload();
  const diagnostics = page.getByTestId("negotiation-timeout-diagnostics");
  await expect(diagnostics).toBeVisible();
  await diagnostics.locator("summary").click();
  await expect(diagnostics).toContainText("acknowledged_usage");
  await expect(diagnostics).toContainText("recent_actions");
});

test("600-second deadline ceilings reach preview for both solver families without launching jobs", async ({
  page,
}) => {
  await page.goto("/");
  const solver = page.getByRole("combobox", { name: "Solver", exact: true });
  const deadline = page.getByLabel("Timeout (seconds)", { exact: true });
  const before = await (await page.request.get("/api/v1/jobs")).json();
  for (const [id, seconds] of [
    ["Decentralized-HeatMap", "600"],
    ["CBS", "600"],
  ]) {
    await solver.selectOption(id);
    await expect(deadline).toHaveAttribute("max", seconds);
    await deadline.fill(seconds);
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/plans/preview") && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Preview effective inputs" })
      .click();
    expect((await response).ok()).toBeTruthy();
    await expect(
      page.getByRole("button", { name: "Run simulation", exact: true }),
    ).toBeEnabled();
  }
  await deadline.fill("600.1");
  const rejected = page.waitForResponse(
    (r) =>
      r.url().endsWith("/plans/preview") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  expect((await rejected).status()).toBe(422);
  const after = await (await page.request.get("/api/v1/jobs")).json();
  expect(after.length).toBe(before.length);
});

test("real scenario: preview, solve, validate, replay, reload, offline export and import", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const jobsBefore = await (await page.request.get("/api/v1/jobs")).json();
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("grid-8x8-4a");
  await page
    .getByRole("combobox", { name: "Setting", exact: true })
    .selectOption("SETTING_4");
  await page
    .getByRole("combobox", { name: "Solver", exact: true })
    .selectOption("Prioritized");
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  await expect(
    page.getByRole("button", { name: "Run simulation", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
    { timeout: 15000 },
  );
  await expect(page.getByTestId("replay-tick")).toContainText("t = 0 /");
  await page.getByRole("button", { name: "Step", exact: true }).click();
  await expect(page.getByTestId("replay-tick")).toContainText("t = 1 /");
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(page.getByTestId("replay-tick")).toContainText("t = 0 /");
  await page.getByRole("button", { name: "agent_0", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "agent_0", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/replay-dark.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
  );
  const jobs = await (await page.request.get("/api/v1/jobs")).json();
  expect(jobs.length).toBe(jobsBefore.length + 1);
  await assertCheckedExportAndImport(page);
  expect(errors).toEqual([]);
});

test("editor validation, undo and immutable scenario save", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("crossing-2a");
  await page.getByLabel("agent_0 starts x").fill("99");
  await page
    .getByRole("button", { name: "Validate draft", exact: true })
    .click();
  await expect(page.getByText(/start \(99, 2\) out of bounds/)).toBeVisible();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.getByLabel("agent_0 starts x")).toHaveValue("0");
  await page
    .getByRole("button", { name: "Save new scenario", exact: true })
    .click();
  await expect(
    page.getByText("Saved a new immutable scenario snapshot"),
  ).toBeVisible();
});

test("comparison and budgeted batch use real committed runs", async ({
  page,
}) => {
  await page.goto("/");
  const admissions = [];
  for (const solver of ["CBS", "Prioritized"]) {
    const r = await page.request.post("/api/v1/jobs", {
      data: {
        scenario_id: "crossing-2a",
        setting: "SETTING_4",
        solver_id: solver,
        timeout_sec: 10,
      },
    });
    expect(r.status()).toBe(202);
    admissions.push(await r.json());
  }
  for (const j of admissions)
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/v1/jobs/${j.job_id}`)).json())
            .state,
        { timeout: 15000 },
      )
      .toBe("completed");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByRole("button", { name: "Refresh library" }).click();
  await page
    .getByRole("combobox", { name: "Left run", exact: true })
    .selectOption(admissions[0].run_id);
  await page
    .getByRole("combobox", { name: "Right run", exact: true })
    .selectOption(admissions[1].run_id);
  await page.getByRole("button", { name: "Build matched cohort" }).click();
  await expect(page.getByText(/Paired: 1 · Common solved: 1/)).toBeVisible();
  await page.screenshot({
    path: "test-results/comparison.png",
    fullPage: true,
  });
  const jobs = [
    {
      scenario_id: "crossing-2a",
      solver_id: "Prioritized",
      setting: "SETTING_4",
      timeout_sec: 10,
    },
  ];
  await page.getByLabel("Batch jobs JSON").fill(JSON.stringify(jobs));
  await page
    .getByRole("button", { name: "Preview batch", exact: true })
    .click();
  await page.getByRole("button", { name: "Run previewed batch" }).click();
  await expect(
    page.getByText("Batch admitted to the bounded local queue"),
  ).toBeVisible();
});

test("local cancellation and two observers do not create duplicate jobs", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  const admission = await page.request.post("/api/v1/jobs", {
    data: {
      scenario_id: "grid-8x8-8a",
      solver_id: "CBS",
      setting: "SETTING_2",
      timeout_sec: 30,
    },
  });
  const j = await admission.json();
  expect(admission.status()).toBe(202);
  const other = await browser.newPage();
  await page.evaluate((id) => localStorage.setItem("mapf-job", id), j.job_id);
  await page.reload();
  await other.goto("/");
  await other.evaluate((id) => localStorage.setItem("mapf-job", id), j.job_id);
  await other.reload();
  // Cancellation remains legal even if this small solver has already completed.
  const cancel = await page.request.post(`/api/v1/jobs/${j.job_id}/cancel`, {
    data: {},
  });
  expect(cancel.status()).toBe(200);
  const terminal = await cancel.json();
  expect(["cancelled", "completed"]).toContain(terminal.state);
  const records = await (await page.request.get("/api/v1/jobs")).json();
  expect(
    records.filter((r: { job_id: string }) => r.job_id === j.job_id),
  ).toHaveLength(1);
  await other.close();
});

test("keyboard, responsive themes and accessibility scan", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Configure experiment" }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to workspace" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  for (const width of [1440, 1100, 800]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const dark = await new AxeBuilder({ page }).analyze();
  expect(dark.violations).toEqual([]);
  await page
    .getByRole("button", { name: "Toggle light or dark theme" })
    .click();
  await page.screenshot({
    path: "test-results/configure-light.png",
    fullPage: true,
  });
  const light = await new AxeBuilder({ page }).analyze();
  expect(light.violations).toEqual([]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    page.getByRole("button", { name: "Preview effective inputs" }),
  ).toBeVisible();
});

test("rectangular coordinates remain selectable after zoom, pan, resize and DPR scaling", async ({
  browser,
}) => {
  const context = await browser.newContext({
    deviceScaleFactor: 2,
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  await openRectangularReplay(page);
  const canvas = page.getByRole("img", { name: /Scenario grid/ });
  await expect(canvas).toBeVisible();
  const box = (await canvas.boundingBox())!;
  const cell = Math.min((box.width - 60) / 6, (box.height - 60) / 3, 60);
  const point = {
    x: (box.width - 6 * cell) / 2 + cell / 2,
    y: (box.height - 3 * cell) / 2 + cell / 2,
  };
  await canvas.click({ position: point });
  await expect(
    page.getByRole("heading", { name: "a", exact: true }),
  ).toBeVisible();
  await assertZoomSelection(page, canvas, point);
  const beforePan = (await canvas.boundingBox())!;
  await page.mouse.move(beforePan.x + point.x + 20, beforePan.y + point.y + 20);
  await page.mouse.down();
  await page.mouse.move(beforePan.x + point.x + 60, beforePan.y + point.y + 40);
  await page.mouse.up();
  await page.getByRole("button", { name: "b", exact: true }).click();
  await canvas.click({ position: { x: point.x + 40, y: point.y + 20 } });
  await expect(
    page.getByRole("heading", { name: "a", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.getByRole("button", { name: "Fit grid", exact: true }).click();
  const resized = (await canvas.boundingBox())!,
    nextCell = Math.min(
      (resized.width - 60) / 6,
      (resized.height - 60) / 3,
      60,
    );
  await page.getByRole("button", { name: "b", exact: true }).click();
  await canvas.click({
    position: {
      x: (resized.width - 6 * nextCell) / 2 + nextCell / 2,
      y: (resized.height - 3 * nextCell) / 2 + nextCell / 2,
    },
  });
  await expect(
    page.getByRole("heading", { name: "a", exact: true }),
  ).toBeVisible();
  expect(await canvas.evaluate((c) => (c as HTMLCanvasElement).width)).toBe(
    Math.round(resized.width * 2),
  );
  await context.close();
});

test("no canvas context keeps non-canvas configuration and errors usable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = () => null;
  });
  await page.goto("/");
  await expect(
    page.getByRole("alert").filter({ hasText: "Canvas is unavailable" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  await expect(
    page.getByRole("button", { name: "Run simulation", exact: true }),
  ).toBeEnabled();
});

test("infeasible no-wait movement stops before executing an illegal action", async ({
  page,
}) => {
  await page.goto("/");
  const response = await page.request.post("/api/v1/jobs", {
    data: {
      grid_width: 3,
      grid_height: 1,
      starts: { a: [0, 0], b: [2, 0] },
      goals: { a: [2, 0], b: [0, 0] },
      obstacles: [],
      setting: "SETTING_1",
      solver_id: "Decentralized-HeatMap",
      max_steps: 3,
      timeout_sec: 5,
    },
  });
  const j = await response.json();
  expect(response.status()).toBe(202);
  await page.evaluate((id) => localStorage.setItem("mapf-job", id), j.job_id);
  await page.reload();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_prefix",
  );
  await expect(page.getByTestId("replay-tick")).toContainText("t = 0 /");
  await expect(
    page.getByRole("button", { name: "First violation", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/infeasible-corridor.png",
    fullPage: true,
  });
});

test("a late scenario response cannot replace the newer selection", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("combobox", { name: "Scenario", exact: true }),
  ).toHaveValue("crossing-2a");
  let release: () => void = () => {},
    entered: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
      release = resolve;
    }),
    arrived = new Promise<void>((resolve) => {
      entered = resolve;
    });
  await page.route("**/api/v1/scenarios/grid-8x8-4a", async (route) => {
    const response = await route.fetch();
    entered();
    await gate;
    await route.fulfill({ response });
  });
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("grid-8x8-4a");
  await arrived;
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("grid-8x8-8a");
  await expect(
    page.getByRole("combobox", { name: "Scenario", exact: true }),
  ).toHaveValue("grid-8x8-8a");
  const oldResponse = page.waitForResponse("**/api/v1/scenarios/grid-8x8-4a");
  release();
  await oldResponse;
  await page.waitForTimeout(50);
  await expect(
    page.getByRole("combobox", { name: "Scenario", exact: true }),
  ).toHaveValue("grid-8x8-8a");
});

test("long replay seeks fetch bounded chunks and deep links restore without submitting", async ({
  page,
}) => {
  const admission = await page.request.post("/api/v1/jobs", {
    data: {
      grid_width: 40,
      grid_height: 2,
      starts: { a: [0, 0] },
      goals: { a: [39, 0] },
      solver_id: "CBS",
      setting: "SETTING_4",
      max_steps: 60,
      timeout_sec: 10,
    },
  });
  expect(admission.status()).toBe(202);
  const job = await admission.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/jobs/${job.job_id}`)).json())
          .state,
      { timeout: 15000 },
    )
    .toBe("completed");
  const requested: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/frames?")) requested.push(r.url());
  });
  await page.goto(`/?run=${job.run_id}&tick=35`);
  await expect(page.getByTestId("replay-tick")).toContainText("t = 35 / 39");
  await expect(
    page.getByRole("cell", { name: "35,0", exact: true }),
  ).toBeVisible();
  expect(requested.some((url) => url.includes("offset=32&limit=32"))).toBe(
    true,
  );
  expect(requested.some((url) => url.includes("offset=0&"))).toBe(false);
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "0,0", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`run=${job.run_id}&tick=0`));
  const before = (await (await page.request.get("/api/v1/jobs")).json()).length;
  await page.reload();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
  );
  expect((await (await page.request.get("/api/v1/jobs")).json()).length).toBe(
    before,
  );
  await assertBoundedReplayMemory(page);
});

test("experiment matrix uses all planned trials and exports the same analysis", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByText("Configure experiment matrix", { exact: true }).click();
  await page.getByLabel("Experiment specification JSON").fill(
    JSON.stringify({
      name: "Browser matrix fixture",
      scenarios: [{ scenario_id: "crossing-2a" }],
      defaults: {
        setting: "SETTING_4",
        recording_level: "metrics-only",
        timeout_sec: 10,
      },
      matrix: { solver_id: ["CBS", "Prioritized"] },
      budget: { workers: 1, wall_seconds: 60, disk_mb: 256, max_trials: 2 },
    }),
  );
  await page
    .getByRole("button", { name: "Preview experiment manifest" })
    .click();
  await expect(page.getByText(/2 planned trials · 1 workers/)).toBeVisible();
  await page.getByRole("button", { name: "Run frozen experiment" }).click();
  await expect(page.getByTestId("experiment-status")).toContainText(
    "completed · 2/2",
    { timeout: 20000 },
  );
  await page
    .getByRole("button", { name: "Analyze all planned trials" })
    .click();
  await expect(page.getByText(/Common solved: 1 · left only: 0/)).toBeVisible();
  await expect(page.getByText("Insufficient independent units")).toHaveCount(2);
  await expect(page.getByTestId("pair-display-count")).toContainText(
    "Showing 1 of 1 pairs",
  );
  await page.getByLabel("Find sampling unit").fill("no-matching-unit");
  await expect(page.getByTestId("pair-display-count")).toContainText(
    "Showing 0 of 1 pairs",
  );
  await expect(page.getByText(/Common solved: 1 · left only: 0/)).toBeVisible();
  await page.getByLabel("Find sampling unit").fill("");
  await page.getByLabel("Show common solved pairs only").check();
  await expect(
    page.getByRole("table", { name: "Paired outcomes" }).locator("tbody tr"),
  ).toHaveCount(1);
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", {
      name: "Export tables and figures (CSV / LaTeX / SVG / PDF)",
    })
    .click();
  const artifact = await download;
  expect(artifact.suggestedFilename()).toBe("experiment-analysis.zip");
  await artifact.saveAs("test-results/experiment-analysis.zip");
});

for (const fault of ["major", "gap"] as const) {
  test(`incompatible event ${fault} stays visible while authoritative polling completes`, async ({
    page,
  }) => {
    await page.route("**/api/v1/jobs/*/stream?*", async (route) => {
      const jobId = new URL(route.request().url()).pathname.split("/").at(-2);
      const event = {
        schema_version: fault === "major" ? "99.0" : "1.0",
        sequence: fault === "gap" ? 99 : 1,
        job_id: jobId,
        run_id: "injected-run",
        attempt_id: "injected-attempt",
        timestamp: Date.now() / 1000,
        type: "status",
        state: "running",
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: ${JSON.stringify(event)}\n\n`,
      });
    });
    await page.goto("/");
    await page
      .getByRole("combobox", { name: "Solver", exact: true })
      .selectOption("CBS");
    await page
      .getByRole("button", { name: "Preview effective inputs" })
      .click();
    await page
      .getByRole("button", { name: "Run simulation", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      fault === "major" ? "Incompatible event schema" : "Event journal gap",
    );
    await expect(page.getByTestId("validation-status")).toHaveText(
      "valid_solution",
      { timeout: 15000 },
    );
    await expect(page.getByRole("alert")).toContainText(
      fault === "major" ? "Incompatible event schema" : "Event journal gap",
    );
  });
}

test("component gallery is a local demonstration with working discrete controls", async ({
  page,
}) => {
  await page.goto("/?components=1");
  await expect(
    page.getByRole("heading", { name: "Workspace component examples" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Step", exact: true }).click();
  await expect(page.getByTestId("replay-tick")).toContainText("t = 1 / 7");
  await page.getByRole("button", { name: "Switch theme" }).click();
  await expect(
    page.getByRole("button", { name: "Unavailable action" }),
  ).toBeDisabled();
});

test("actual decision heat survives replay, checked import and offline viewing, with explicit budget gaps", async ({
  page,
}) => {
  const run = await executeHeatRun(page, 250000);
  const frame = run.frames.find(
    (f: { local_heat: { fields: unknown[]; required_entries: number }[] }) =>
      f.local_heat.some((h) => h.required_entries > 0),
  );
  expect(frame).toBeTruthy();
  const record = frame.local_heat.find(
    (h: { required_entries: number }) => h.required_entries > 0,
  );
  await page.goto(`/?run=${run.metadata.run_id}&tick=${frame.tick}`);
  await page
    .getByRole("button", { name: record.agent_id, exact: true })
    .click();
  await page.getByLabel("Recorded local heat", { exact: true }).check();
  await page
    .getByLabel("Recorded heat decision", { exact: true })
    .selectOption(record.record_id);
  await page.getByLabel("Heat time slice", { exact: true }).selectOption("0");
  await expect(
    page.getByText(`Decision t=${record.tick}; agent ${record.agent_id};`, {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByText("Recorded heat values", { exact: true }).click();
  await assertHeatInspectorKeyboardAccess(page);
  const values = page.getByRole("table", { name: "Recorded heat values" });
  expect(await values.locator("tbody tr").count()).toBe(
    Object.keys(record.fields[0]).length,
  );
  await page.screenshot({
    path: "test-results/actual-decision-heat.png",
    fullPage: true,
  });
  for (const [cell, value] of Object.entries(record.fields[0]).slice(0, 3)) {
    await expect(
      values
        .getByRole("row")
        .filter({ has: page.getByRole("cell", { name: cell, exact: true }) }),
    ).toContainText(String(value));
  }
  await assertOfflineHeat(page, run.metadata.run_id, frame, record);
  const limited = await executeHeatRun(page, 0);
  const missing = limited.frames.find(
    (f: { local_heat: { status: string }[] }) =>
      f.local_heat.some((h) => h.status === "budget_exhausted"),
  );
  const omitted = missing.local_heat.find(
    (h: { status: string }) => h.status === "budget_exhausted",
  );
  await page.goto(`/?run=${limited.metadata.run_id}&tick=${missing.tick}`);
  await page
    .getByRole("button", { name: omitted.agent_id, exact: true })
    .click();
  await page.getByLabel("Recorded local heat", { exact: true }).check();
  await page
    .getByLabel("Recorded heat decision", { exact: true })
    .selectOption(omitted.record_id);
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Local heat recording budget exhausted" }),
  ).toBeVisible();
});

async function assertCheckedExportAndImport(page: Page) {
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Complete bundle" }).click();
  const file = await download;
  await file.saveAs("test-results/exported-bundle.json");
  const bundle = JSON.parse(
    await fs.readFile("test-results/exported-bundle.json", "utf8"),
  );
  expect(bundle.payload.result.frames[0].positions.agent_0).toEqual([0, 0]);
  await page
    .getByLabel("Import checked replay bundle")
    .setInputFiles("test-results/exported-bundle.json");
  await expect(
    page.getByText("Bundle integrity and trajectory receipt verified"),
  ).toBeVisible();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
  );
  await page.getByRole("button", { name: "Export", exact: true }).click();
  const htmlDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Offline HTML replay" }).click();
  const htmlFile = await htmlDownload;
  await htmlFile.saveAs("test-results/replay.html");
  const html = await fs.readFile("test-results/replay.html", "utf8");
  const offline = await page.context().newPage();
  await offline.route("**/*", (route) => route.abort());
  await offline.setContent(html);
  await expect(
    offline.getByText("DEC-MAPF offline replay", { exact: true }),
  ).toBeVisible();
  await offline.getByRole("button", { name: "Next", exact: true }).click();
  await expect(offline.locator("#time")).toHaveText("t=1");
  await offline.close();
}

async function openRectangularReplay(page: Page) {
  await page.goto("http://127.0.0.1:8765/");
  const response = await page.request.post("/api/v1/jobs", {
    data: {
      grid_width: 6,
      grid_height: 3,
      starts: { a: [0, 0], b: [5, 2] },
      goals: { a: [5, 0], b: [0, 2] },
      obstacles: [],
      setting: "SETTING_4",
      solver_id: "Prioritized",
      timeout_sec: 10,
    },
  });
  expect(response.status()).toBe(202);
  const j = await response.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/jobs/${j.job_id}`)).json())
          .state,
    )
    .toBe("completed");
  await page.evaluate((id) => localStorage.setItem("mapf-job", id), j.job_id);
  await page.reload();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
  );
}

async function assertZoomSelection(
  page: Page,
  canvas: Locator,
  point: { x: number; y: number },
) {
  // Zoom preserves the cell's canvas-relative coordinate. Table focus may scroll
  // an ancestor, so a saved page coordinate is not a stable click target.
  const pixelsBeforeZoom = await canvas.evaluate((c) =>
    (c as HTMLCanvasElement).toDataURL(),
  );
  const wheelRendered = canvas.evaluate(
    (c) =>
      new Promise<void>((resolve) => {
        c.addEventListener(
          "wheel",
          () => requestAnimationFrame(() => resolve()),
          {
            once: true,
          },
        );
      }),
  );
  const beforeZoom = (await canvas.boundingBox())!;
  await page.mouse.move(beforeZoom.x + point.x, beforeZoom.y + point.y);
  await page.mouse.wheel(0, -100);
  await wheelRendered;
  await expect
    .poll(() => canvas.evaluate((c) => (c as HTMLCanvasElement).toDataURL()))
    .not.toBe(pixelsBeforeZoom);
  await page.getByRole("button", { name: "b", exact: true }).click();
  await canvas.click({ position: point });
  await expect(
    page.getByRole("heading", { name: "a", exact: true }),
  ).toBeVisible();
}

async function assertBoundedReplayMemory(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  await cdp.send("HeapProfiler.collectGarbage");
  const heap = async () =>
    Number(
      (await cdp.send("Performance.getMetrics")).metrics.find(
        (m) => m.name === "JSHeapUsedSize",
      )?.value || 0,
    );
  const initialHeap = await heap();
  for (let i = 0; i < 20; i++) {
    await page.getByRole("button", { name: "Compare", exact: true }).click();
    await page.getByRole("button", { name: "Inspect", exact: true }).click();
  }
  await cdp.send("HeapProfiler.collectGarbage");
  const retainedHeap = await heap();
  await fs.writeFile(
    "test-results/replay-memory.json",
    JSON.stringify({
      cycles: 20,
      initialHeap,
      retainedHeap,
      scope: "Chrome JS heap after GC; excludes native canvas/GPU memory",
    }),
  );
  expect(retainedHeap - initialHeap).toBeLessThan(8 * 1024 * 1024);
  await cdp.detach();
}

async function executeHeatRun(page: Page, limit: number) {
  const data = {
    grid_width: 5,
    grid_height: 5,
    starts: { a: [0, 2], b: [4, 2], c: [2, 0] },
    goals: { a: [4, 2], b: [0, 2], c: [2, 4] },
    solver_id: "Decentralized-HeatMap",
    setting: "SETTING_4",
    fov_size: 5,
    initial_tokens: 5,
    timeout_sec: null,
    max_steps: 32,
    recording_level: "full-trace",
  };
  const response = await page.request.post("/api/v1/jobs", {
    data: { ...data, heat_recording_limit: limit },
  });
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/jobs/${job.job_id}`)).json())
          .state,
    )
    .toBe("completed");
  return (await page.request.get(`/api/v1/runs/${job.run_id}`)).json();
}

async function assertHeatInspectorKeyboardAccess(page: Page) {
  const replayAccessibility = await new AxeBuilder({ page }).analyze();
  expect(replayAccessibility.violations).toEqual([]);
  const metadata = page.locator("details").filter({
    has: page.locator("summary", { hasText: "Run metadata · MANIFEST #1" }),
  });
  await metadata.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(metadata.getByRole("button")).toHaveCount(0);
  const payload = metadata.locator("pre");
  await payload.focus();
  await expect(payload).toBeFocused();
  await metadata.locator("summary").click();
  const contracts = page.locator(".inspector-panel > pre");
  await contracts.focus();
  await expect(contracts).toBeFocused();
  await page.keyboard.press("End");
  await expect
    .poll(() => contracts.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  const movement = page
    .locator("details")
    .filter({ has: page.locator("summary", { hasText: /^t=1 · MOVE/ }) })
    .first();
  await movement.locator("summary").click();
  await movement
    .getByRole("button", { name: "Jump to t=1", exact: true })
    .click();
  await expect(page.getByTestId("replay-tick")).toContainText("t = 1 /");
  await movement.locator("summary").click();
}

async function assertOfflineHeat(
  page: Page,
  runId: string,
  frame: FrameSnapshot,
  record: DecisionHeatRecord,
) {
  const bundle = await (
    await page.request.get(`/api/v1/runs/${runId}/export/json`)
  ).json();
  const imported = await page.request.post("/api/v1/runs/import", {
    data: bundle,
  });
  expect(imported.ok()).toBeTruthy();
  const importedId = (await imported.json()).run_id;
  expect(
    (await (await page.request.get(`/api/v1/runs/${importedId}`)).json())
      .frames[frame.tick].local_heat,
  ).toEqual(frame.local_heat);
  const html = await (
    await page.request.get(`/api/v1/runs/${importedId}/export/html`)
  ).text();
  const offline = await page.context().newPage();
  await offline.route("**/*", (route) => route.abort());
  await offline.setContent(html);
  await offline.locator("#tick").fill(String(frame.tick));
  await offline.locator("#heat").selectOption(record.record_id);
  await offline.locator("#heat-slice").selectOption("0");
  await expect(offline.locator("#heat-status")).toContainText(
    `decision t=${record.tick}`,
  );
  await expect(offline.locator("#details")).toContainText(
    '"actual_strategy_weights"',
  );
  await offline.screenshot({
    path: "test-results/offline-decision-heat.png",
    fullPage: true,
  });
  await offline.close();
}
