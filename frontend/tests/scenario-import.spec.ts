import { test, expect } from "@playwright/test";
import { parseScenarioDraft, scenarioDraftInput } from "../src/scenarioDraft";

const example = {
  name: "Unvalidated import",
  grid_width: 4,
  grid_height: 3,
  starts: { second: [0, 0], first: [1, 0] },
  goals: { first: [2, 0], second: [3, 0] },
  obstacles: [],
  setting: "SETTING_2",
  agent_order: ["first", "second"],
};

test("JSON shape checks reject malformed coordinates and rosters before rendering", () => {
  for (const value of [
    null,
    [],
    { ...example, grid_width: 1.5 },
    { ...example, starts: "bad" },
    { ...example, goals: { first: [2, 0] } },
    { ...example, starts: { first: [0], second: [1, 2] } },
    { ...example, obstacles: [[1, "2"]] },
    { ...example, setting: "UNKNOWN" },
    { ...example, agent_order: ["first", "first"] },
    { ...example, agent_order: ["first", "other"] },
  ]) {
    expect(() => parseScenarioDraft(JSON.stringify(value))).toThrow();
  }
});

test("an imported draft preserves coordinates and order while leaving physical checks to the backend", () => {
  const draft = parseScenarioDraft(
    JSON.stringify({
      ...example,
      starts: { second: [-1, 0], first: [1, 0] },
      scenario_id: "stale-saved-id",
      instance_hash: "stale-digest",
    }),
  );
  expect(draft.scenario_id).toBeNull();
  expect(draft.instance_hash).toBe("");
  expect(draft.starts.second).toEqual([-1, 0]);
  const request = scenarioDraftInput(draft);
  expect(Object.keys(request.starts)).toEqual(["first", "second"]);
  expect(request.goals).toEqual(example.goals);
  expect(request).not.toHaveProperty("instance_hash");
});

test("a malformed JSON roster keeps the editable scenario intact", async ({
  page,
}) => {
  await page.goto("/");
  const original = page.getByLabel("agent_0 starts x", { exact: true });
  await expect(original).toHaveValue("0");
  await page
    .getByText("JSON import / keyboard obstacle editing", { exact: true })
    .click();
  await page.getByRole("button", { name: "Copy draft into editor" }).click();
  const editor = page.getByLabel("Scenario JSON");
  const draft = JSON.parse(await editor.inputValue());
  delete draft.goals.agent_0;
  await editor.fill(JSON.stringify(draft));
  await page.getByRole("button", { name: "Load JSON draft" }).click();
  await expect(page.getByRole("alert")).toContainText("roster");
  await expect(original).toHaveValue("0");
});

test("copying a draft preserves its explicit agent order", async ({ page }) => {
  await page.goto("/");
  await page
    .getByText("JSON import / keyboard obstacle editing", { exact: true })
    .click();
  const editor = page.getByLabel("Scenario JSON");
  await page.getByRole("button", { name: "Copy draft into editor" }).click();
  const draft = JSON.parse(await editor.inputValue());
  const ids = Object.keys(draft.starts).reverse();
  draft.agent_order = ids;
  await editor.fill(JSON.stringify(draft));
  await page.getByRole("button", { name: "Load JSON draft" }).click();
  await page.getByRole("button", { name: "Copy draft into editor" }).click();
  expect(Object.keys(JSON.parse(await editor.inputValue()).starts)).toEqual(
    ids,
  );
});
