import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { createServer, type Server } from "node:http";
import fs from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { pathToFileURL } from "node:url";

const root = resolve("../.docs-build/site");
let server: Server;
let url: string;
test.beforeAll(async () => {
  await fs.access(resolve(root, "index.html"));
  server = createServer(async (req, res) => {
    const file = resolve(
      root,
      "." + decodeURIComponent((req.url || "/").split("?")[0]),
    );
    if (file !== root && !file.startsWith(root + sep)) {
      res.writeHead(403).end();
      return;
    }
    try {
      const path = (await fs.stat(file)).isDirectory()
        ? resolve(file, "index.html")
        : file;
      const types: Record<string, string> = {
        ".html": "text/html",
        ".js": "text/javascript",
        ".json": "application/json",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
      };
      res.setHeader(
        "Content-Type",
        types[extname(path)] || "application/octet-stream",
      );
      res.end(await fs.readFile(path));
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("No local docs address");
  url = `http://127.0.0.1:${address.port}`;
});
test.afterAll(async () => {
  await new Promise<void>((done) => server?.close(() => done()));
});

test("narrated replay works offline with event and frame references", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/^https?:/, (route) => route.abort());
  await page.goto(
    pathToFileURL(resolve("../docs/assets/narrative/negotiation-story.html"))
      .href,
  );
  await expect(
    page.getByRole("heading", { name: "Follow one recorded negotiation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /settlement · t=/ }).click();
  await expect(page.locator("#story-text")).toContainText("zero");
  await page
    .getByRole("button", { name: /move · t=/ })
    .first()
    .click();
  await expect(page.locator("#time")).toHaveText("t=1");
  await page.getByText("Exact evidence for this step", { exact: true }).click();
  await expect(page.locator("#story-evidence")).toContainText("sequence=");
  await page.screenshot({
    path: "test-results/narrated-replay.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("local documentation search leads to the actual study guide", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(url);
  const search = page.getByRole("textbox", { name: "Search" });
  await search.fill("study");
  const results = page.locator(".md-search-result");
  await expect(results).toContainText("Start a study", { timeout: 10000 });
  await results.locator('a[href*="docs/NEW-STUDY.html"]').first().click();
  await expect(
    page.getByRole("heading", { name: /Start a study you can inspect/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/searchable-docs.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("homepage gallery cards open their rendered guide and load real images", async ({
  page,
}) => {
  for (let index = 0; index < 4; index++) {
    await page.goto(url);
    await page.locator(".md-content table a:has(img)").nth(index).click();
    await expect(
      page.getByRole("heading", {
        name: /^Dense interactions, visible decisions/,
      }),
    ).toBeVisible();
    const images = page.locator('.md-content img[src*="assets/gallery/"]');
    await expect(
      images.locator('xpath=self::img[contains(@src,".png")]'),
    ).toHaveCount(6);
    await expect(
      images.locator('xpath=self::img[contains(@src,".gif")]'),
    ).toHaveCount(1);
    await expect
      .poll(async () =>
        images.evaluateAll((elements) =>
          elements.every(
            (element) =>
              element instanceof HTMLImageElement &&
              element.complete &&
              element.naturalWidth > 0,
          ),
        ),
      )
      .toBe(true);
  }
});

test("documentation home and gallery play the replay and open its full-resolution GIF", async ({
  page,
}) => {
  for (const path of ["/", "/docs/GALLERY.html"]) {
    await page.goto(url + path);
    const replay = page.locator('img[src$="negotiation-agent-2.gif"]');
    await replay.scrollIntoViewIfNeeded();
    await expect
      .poll(() =>
        replay.evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBe(1024);
    const digest = (bytes: Buffer) =>
      createHash("sha256").update(bytes).digest("hex");
    const first = digest(await replay.screenshot());
    // Longer than the initial two-second and final three-second holds.
    await page.waitForTimeout(3400);
    expect(digest(await replay.screenshot())).not.toBe(first);
    await replay.click();
    await expect(page).toHaveURL(/negotiation-agent-2-2048\.gif$/);
    await expect
      .poll(() =>
        page
          .locator("img")
          .evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBe(2048);
  }
});
