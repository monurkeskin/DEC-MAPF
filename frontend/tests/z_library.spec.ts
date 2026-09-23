import { expect, test } from "@playwright/test";

test("real library pages beyond 100 imported copies and exposes older runs to comparison", async ({
  page,
}) => {
  // One actual solver result, imported repeatedly into this test-owned workspace.
  // These copies exercise storage/UI scale; they are not independent experiments.
  const submitted = await page.request.post("/api/v1/jobs", {
    data: {
      scenario_id: "crossing-2a",
      solver_id: "CBS",
      setting: "SETTING_4",
      timeout_sec: 10,
    },
  });
  expect(submitted.status()).toBe(202);
  const { job_id } = await submitted.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/v1/jobs/${job_id}`)).json()).state,
    )
    .toBe("completed");
  const job = await (await page.request.get(`/api/v1/jobs/${job_id}`)).json();
  const bundle = await (
    await page.request.get(`/api/v1/runs/${job.run_id}/export/json`)
  ).json();
  const solverName = bundle.payload.metadata.solver_name;
  for (let index = 0; index < 105; index++) {
    expect(
      (
        await page.request.post("/api/v1/runs/import", { data: bundle })
      ).status(),
    ).toBe(201);
  }
  const first = await (
    await page.request.get(
      `/api/v1/runs/page?limit=100&solver_name=${encodeURIComponent(solverName)}`,
    )
  ).json();
  expect(first.items.length).toBe(100);
  const last = await (
    await page.request.get(
      `/api/v1/runs/page?limit=100&solver_name=${encodeURIComponent(solverName)}&cursor=${encodeURIComponent(first.next_cursor)}`,
    )
  ).json();
  const older = last.items.at(-1).run_id;
  await page.goto("/");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Library solver", exact: true })
    .selectOption(solverName);
  await page.getByRole("button", { name: "Apply library filters" }).click();
  await expect(
    page.getByText(`Saved runs (100 / ${first.total})`, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Load more runs", exact: true })
    .click();
  await expect(
    page.getByText(`Saved runs (${first.total} / ${first.total})`, {
      exact: true,
    }),
  ).toBeVisible();
  const selected = page.waitForResponse((response) =>
    response.url().includes(`/runs/${older}`),
  );
  await page
    .locator(".library-row")
    .getByRole("button", { name: new RegExp(` · ${older.slice(-8)}$`) })
    .click();
  expect((await selected).ok()).toBeTruthy();
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Left run", exact: true })
    .selectOption(older);
  await page
    .getByRole("textbox", { name: "Library experiment ID", exact: true })
    .fill("absent-browser-fixture");
  await page.getByRole("button", { name: "Apply library filters" }).click();
  await expect(page.getByText("No runs match these filters.")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Left run", exact: true }),
  ).toHaveValue(older);
  await page.screenshot({
    path: "test-results/library-empty-filter.png",
    fullPage: true,
  });
});

test("preview explains setting-dependent scientific assumptions before execution", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Setting", exact: true })
    .selectOption("SETTING_1");
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  const card = page.getByLabel("Problem assumptions", { exact: true });
  await expect(card).toContainText("Waiting before the goal: forbidden");
  await expect(card).toContainText("Goal policy: stay");
  await expect(card).toContainText("Initial positions are t=0");
  await page
    .getByRole("combobox", { name: "Setting", exact: true })
    .selectOption("SETTING_4");
  await expect(card).toHaveCount(0);
  await page.getByRole("button", { name: "Preview effective inputs" }).click();
  await expect(card).toContainText("Goal policy: disappear");
  await expect(card).toContainText("Waiting before the goal: allowed");
});
