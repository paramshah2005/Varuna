import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

test("stale plans explain rerunning and current plans lead to approval controls", async ({
  page,
  request,
}) => {
  const scenario = JSON.parse(
    await readFile(
      new URL("../../data/compound.json", import.meta.url),
      "utf8",
    ),
  );
  scenario.scenario_id = `approval-${randomUUID().slice(0, 8)}`;
  scenario.name = `Approval recovery ${scenario.scenario_id}`;
  const created = await request.post("/api/scenarios", { data: scenario });
  expect(created.status()).toBe(201);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByLabel("Choose a scenario").selectOption(scenario.scenario_id);
  await page
    .getByRole("switch", { name: "Agents active", exact: true })
    .uncheck();
  await page
    .getByRole("button", { name: "Run Simulation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review response plan" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Review response plan" }).click();
  await expect(
    page.getByRole("region", { name: "Response plan", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "Verified response plan", exact: true }),
  ).toBeInViewport();
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Select zone A, Riverside" }).click();
  await page
    .getByRole("spinbutton", { name: "Baseline demand", exact: true })
    .fill("33");
  await page
    .getByRole("button", { name: "Apply changes", exact: true })
    .click();
  await expect(page.getByText("Rerun required", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Review response plan" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Rerun applied scenario v2", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review response plan" }),
  ).toBeEnabled();
  await expect(page.getByText("Rerun required", { exact: true })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Review response plan" }).click();
  await expect(
    page.getByRole("button", { name: "Approve exact plan" }),
  ).toBeEnabled();
  const runs = (await (await request.get("/api/runs")).json()).runs.filter(
    (run: { scenario_id: string }) => run.scenario_id === scenario.scenario_id,
  );
  expect(
    runs.map((run: { scenario_version: number }) => run.scenario_version),
  ).toEqual([1, 2]);
  expect(
    runs.every((run: { status: string }) => run.status === "awaiting_approval"),
  ).toBe(true);
});
