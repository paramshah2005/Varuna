import { test, expect } from "@playwright/test";
test("WebGL fallback, schema errors, connection edits and JSON import", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type === "webgl" || type === "webgl2") return null;
      return original.apply(this, [type, ...args] as Parameters<
        typeof original
      >);
    } as typeof original;
  });
  await page.goto("/");
  await expect(page.locator(".accent-fallback").first()).toBeVisible();
  await page
    .getByRole("switch", { name: "Agents active", exact: true })
    .uncheck();
  await page
    .getByRole("button", { name: "Run Simulation", exact: true })
    .click();
  await expect(page.getByTestId("simulation-map")).toBeVisible();
  const demand = page.getByRole("spinbutton", {
    name: "Baseline demand",
    exact: true,
  });
  await demand.fill("1");
  await page.getByRole("button", { name: "Preview effects" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Critical demand must be included",
  );
  await page.getByRole("button", { name: "Reset draft" }).click();
  await page
    .getByRole("button", { name: "Edit connection A-B", exact: true })
    .click();
  await page
    .getByRole("combobox")
    .filter({ has: page.locator('option[value="closed"]') })
    .selectOption("closed");
  await page.getByRole("button", { name: "Done · keep in draft" }).click();
  await page.getByRole("button", { name: "Preview effects" }).click();
  await expect(page.getByText("DRAFT PREVIEW", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reset draft" }).click();
  const bootstrap = await (await page.request.get("/api/bootstrap")).json();
  const scenario = bootstrap.scenarios.find(
    (s: { scenario_id: string }) => s.scenario_id === "normal",
  );
  const fileChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Import JSON" }).click();
  await (
    await fileChooser
  ).setFiles({
    name: "normal.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(scenario)),
  });
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Scenario imported and validated" }),
  ).toContainText("Scenario imported and validated");
});
test("infeasible plans cannot be approved and station closure reroutes", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Choose a scenario" })
    .selectOption("infeasible");
  await page
    .getByRole("button", { name: "Run Simulation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Essential supply shortfall · escalate",
    }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeDisabled();
  await page.goto("/public");
  await page
    .getByRole("combobox", { name: "Your demo neighborhood" })
    .selectOption("C");
  await page.getByRole("button", { name: "Find a cooling center" }).click();
  await expect(
    page.getByRole("heading", { name: "Garden District Cooling Center" }),
  ).toBeVisible();
  await page
    .getByRole("switch", { name: "Simulate station C closure" })
    .check();
  await page.getByRole("button", { name: "Find a cooling center" }).click();
  await expect(
    page.getByRole("heading", { name: "Garden District Cooling Center" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("minutes on a synthetic walking graph"),
  ).toBeVisible();
});
