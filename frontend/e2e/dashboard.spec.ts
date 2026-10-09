import { test, expect } from "@playwright/test";
test("run reveal, editing, exact approval and persisted evidence", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Water resilience, in focus.")).toBeVisible();
  await expect(page.getByTestId("simulation-map")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Run Simulation", exact: true })
    .click();
  await expect(page.getByTestId("simulation-map")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeEnabled({ timeout: 30000 });
  await page.getByRole("button", { name: "Approve exact plan" }).click();
  await expect(
    page.getByRole("button", { name: "Open evidence report" }),
  ).toBeEnabled({ timeout: 30000 });
  const evidenceDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Open evidence report" }).click();
  const evidence = await evidenceDownload;
  expect(evidence.suggestedFilename()).toMatch(/^aquaagent-.*\.json$/);
  const fs = await import("node:fs/promises");
  const report = JSON.parse(
    await fs.readFile((await evidence.path())!, "utf8"),
  );
  expect(report.approved.verified).toBe(true);
  expect(report.run_id).toBeTruthy();
  expect(report.approved.totals.critical_percent).toBe(100);
  for (const metric of ["demand", "supply", "shortage"]) {
    await expect(page.getByTestId(`${metric}-chart`)).toBeVisible();
  }
  await page.getByRole("button", { name: "Select zone A, Riverside" }).click();
  const supplyChart = page.getByTestId("supply-chart");
  await supplyChart.getByText("View measured values").click();
  const finalBaselineA = report.baseline.time_series
    .at(-1)
    .zones.find((zone: { id: string }) => zone.id === "A");
  const finalApprovedA = report.approved.time_series
    .at(-1)
    .zones.find((zone: { id: string }) => zone.id === "A");
  const supplyRow = supplyChart.locator("tbody tr").last();
  await expect(supplyRow.locator("td").nth(1)).toHaveText(
    (finalBaselineA.external / report.baseline.step_hours).toFixed(2),
  );
  await expect(supplyRow.locator("td").nth(2)).toHaveText(
    (finalApprovedA.external / report.approved.step_hours).toFixed(2),
  );
  const demand = page.getByRole("spinbutton", {
    name: "Baseline demand",
    exact: true,
  });
  await demand.fill("39");
  await page.getByRole("button", { name: "Preview effects" }).click();
  await expect(page.getByText("DRAFT PREVIEW", { exact: true })).toBeVisible();
  await expect(
    page.getByTestId("demand-chart").getByText(/Draft preview:/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Apply changes" }).click();
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeDisabled();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await downloadPromise).suggestedFilename()).toContain(
    "aquaagent-compound-v",
  );
  await page.getByRole("button", { name: "Reset draft" }).click();
  await expect(demand).toHaveValue("34");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});
test("public station route and manual location fallback", async ({ page }) => {
  await page.goto("/public");
  await expect(page.getByText("A cooler place.")).toBeVisible();
  await page.getByRole("button", { name: "Find a cooling center" }).click();
  await expect(
    page.getByText("minutes on a synthetic walking graph"),
  ).toBeVisible();
  await expect(
    page.getByText("Reported open · water available · capacity available"),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});
test("reduced motion and keyboard graph selection", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Run Simulation", exact: true })
    .click();
  const zone = page.getByRole("button", {
    name: "Select zone B, Civic Quarter",
  });
  await zone.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Zone B · Civic Quarter" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
  ).toBe(false);
});
