import { test, expect } from "@playwright/test";
import { initialLayers, toggleLayer } from "../src/hooks/useReplayLayers";

test("recorded and hindsight heat remain exclusive without mutating the previous view", () => {
  const recorded = toggleLayer(initialLayers, "localHeat", true);
  const hindsight = toggleLayer(recorded, "heat", true);
  expect(recorded).toEqual({ ...initialLayers, localHeat: true });
  expect(hindsight).toEqual({ ...initialLayers, heat: true });
  expect(toggleLayer(hindsight, "localHeat", true)).toEqual(recorded);
  expect(toggleLayer(recorded, "fov", true)).toEqual({
    ...recorded,
    fov: true,
  });
  expect(toggleLayer(recorded, "localHeat", false)).toEqual(initialLayers);
});

test("inspection layers persist across workflow tabs", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("FoV geometry", { exact: true }).check();
  await page.getByLabel("Recorded local heat", { exact: true }).check();
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await page.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(page.getByLabel("FoV geometry", { exact: true })).toBeChecked();
  await expect(
    page.getByLabel("Recorded local heat", { exact: true }),
  ).toBeChecked();
  await page.getByLabel("Hindsight heat", { exact: true }).check();
  await expect(
    page.getByLabel("Recorded local heat", { exact: true }),
  ).not.toBeChecked();
});

for (const action of ["Undo", "Redo"]) {
  test(`a late scenario response cannot overwrite ${action.toLowerCase()}`, async ({
    page,
  }) => {
    await page.goto("/");
    const coordinate = page.getByLabel("agent_0 starts x", { exact: true });
    await expect(coordinate).toHaveValue("0");
    await coordinate.fill("1");
    if (action === "Redo")
      await page.getByRole("button", { name: "Undo", exact: true }).click();
    let release!: () => void;
    let arrived!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const entered = new Promise<void>((resolve) => {
      arrived = resolve;
    });
    await page.route("**/api/v1/scenarios/grid-8x8-4a", async (route) => {
      const response = await route.fetch();
      arrived();
      await gate;
      await route.fulfill({ response });
    });
    const select = page.getByRole("combobox", {
      name: "Scenario",
      exact: true,
    });
    await select.selectOption("grid-8x8-4a");
    await entered;
    await page.getByRole("button", { name: action, exact: true }).click();
    const response = page.waitForResponse("**/api/v1/scenarios/grid-8x8-4a");
    release();
    await response;
    await page.waitForTimeout(50);
    await expect(select).toHaveValue("");
    await expect(coordinate).toHaveValue(action === "Undo" ? "0" : "1");
  });
}
