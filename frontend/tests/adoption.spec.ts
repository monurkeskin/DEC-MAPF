import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";

test("first session preserves advanced choices and exports identical headless inputs", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your first checked replay" }),
  ).toBeVisible();
  const advanced = page.getByText("Advanced solver parameters", {
    exact: true,
  });
  const protocol = page.getByRole("combobox", {
    name: /^Negotiation protocol/,
  });
  await expect(protocol).not.toBeVisible();
  await advanced.click();
  await protocol.selectOption("taop-v1");
  await advanced.click();
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/plans/preview"),
  );
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  const preview = await (await response).json();
  expect(preview.plans[0].effective_config.negotiation_protocol).toBe(
    "taop-v1",
  );
  await page
    .getByText("Run these inputs without the GUI", { exact: true })
    .click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download headless study" }).click();
  const file = await (await download).path();
  const spec = JSON.parse(await fs.readFile(file!, "utf8"));
  const compiled = await page.request.post("/api/v1/experiments/preview", {
    data: spec,
  });
  expect(compiled.ok()).toBeTruthy();
  const manifest = await compiled.json();
  expect(manifest.trials[0].plan.definition_digest).toBe(
    preview.plans[0].definition_digest,
  );
  const {
    scenario_id: _id,
    description: _description,
    ...geometry
  } = preview.plans[0].scenario;
  expect(manifest.trials[0].plan.scenario).toEqual(geometry);
  await advanced.click();
  await expect(protocol).toHaveValue("taop-v1");
  await protocol.selectOption("taop-v2");
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  await page
    .getByRole("button", { name: "Run simulation", exact: true })
    .click();
  await expect(page.getByTestId("validation-status")).toHaveText(
    "valid_solution",
    { timeout: 15000 },
  );
  await page.reload();
  await expect(page.getByTestId("evidence-mode")).toContainText("Saved replay");
  await expect(page.locator(".status-strip")).not.toContainText(
    "Not connected",
  );
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole("button", { name: "Configure", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Scenario", exact: true })
    .selectOption("grid-8x8-4a");
  const nextPreview = page.waitForResponse((r) =>
    r.url().endsWith("/plans/preview"),
  );
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  expect((await nextPreview).ok()).toBeTruthy();
});

test("saved inputs preserve nonalphabetic roster order and optional horizons in a portable study", async ({
  page,
}) => {
  const admitted = await page.request.post("/api/v1/jobs", {
    data: {
      grid_width: 4,
      grid_height: 3,
      setting: "SETTING_4",
      solver_id: "CBS",
      starts: { z: [0, 0], a: [0, 2] },
      goals: { z: [3, 0], a: [3, 2] },
      broadcast_horizon: 4,
      negotiation_horizon: 2,
      timeout_sec: 10,
    },
  });
  expect(admitted.status()).toBe(202);
  const job = await admitted.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/jobs/${job.job_id}`)).json())
          .state,
    )
    .toBe("completed");
  const original = await (
    await page.request.get(`/api/v1/runs/${job.run_id}`)
  ).json();
  expect(original.metadata.instance.agent_order).toEqual(["z", "a"]);
  await page.goto(`/?run=${job.run_id}`);
  await expect(page.getByTestId("evidence-mode")).toContainText("Saved replay");
  await page.getByRole("button", { name: "Configure", exact: true }).click();
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/plans/preview"),
  );
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  const planResponse = await response;
  expect(planResponse.ok()).toBeTruthy();
  const plan = (await planResponse.json()).plans[0];
  expect(plan.scenario.agent_order).toEqual(["z", "a"]);
  expect(plan.effective_config.broadcast_horizon).toBe(4);
  expect(plan.effective_config.negotiation_horizon).toBe(2);
  expect(plan.definition_digest).toBe(original.metadata.definition_digest);
  await page
    .getByText("Run these inputs without the GUI", { exact: true })
    .click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download headless study" }).click();
  const spec = JSON.parse(
    await fs.readFile((await (await download).path())!, "utf8"),
  );
  const compiled = await page.request.post("/api/v1/experiments/preview", {
    data: spec,
  });
  expect(compiled.ok()).toBeTruthy();
  expect((await compiled.json()).trials[0].plan.definition_digest).toBe(
    plan.definition_digest,
  );
});
