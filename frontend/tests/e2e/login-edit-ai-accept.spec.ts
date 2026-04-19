import { expect, test } from "@playwright/test";

function buildSseEvent(event: string, payload: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

test("login, edit, and accept an AI rewrite", async ({ browser, page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "PreviewPass123!";
  const workspaceId = `ws-e2e-${Date.now()}`;
  const title = `Playwright Doc ${Date.now()}`;
  const originalText = "This draft sentence needs a clearer rewrite.";
  const acceptedText = "This draft sentence now reads more clearly and directly.";
  const jobId = "job-e2e-1";
  const suggestionId = "suggestion-e2e-1";

  await page.goto("/");

  await page.getByRole("button", { name: /register/i }).click();
  await page.getByLabel("Display Name").fill("E2E User");
  await page.getByLabel("Email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /create account/i }).click();

  await expect(page.getByRole("heading", { name: /my documents/i })).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole("button", { name: /\+ new document/i }).click();
  await page.getByLabel("Workspace ID").fill(workspaceId);
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: /^Create$/ }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("Connected")).toBeVisible({ timeout: 15_000 });

  const editor = page.locator(".ProseMirror").first();
  await expect(editor).toBeVisible();
  await editor.click();
  await page.keyboard.type(originalText);

  const saveButton = page.getByRole("button", { name: /^Save now$/ });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByRole("button", { name: /^Saved$/ })).toBeDisabled();

  await page.route(/\/api\/documents\/[^/]+\/ai-jobs\/stream$/, async (route) => {
    const body = route.request().postDataJSON() as { selected_text?: string };
    expect(body.selected_text).toBe(originalText);

    const sseBody = [
      buildSseEvent("job", {
        job_id: jobId,
        status: "running",
        provider_name: "test-double",
        model_name: "playwright",
      }),
      buildSseEvent("delta", {
        job_id: jobId,
        delta: acceptedText,
      }),
      buildSseEvent("suggestion", {
        suggestion_id: suggestionId,
        original_text: originalText,
        suggested_text: acceptedText,
        diff_json: null,
        stale: false,
        disposition: "pending",
        partial_output_available: false,
      }),
      buildSseEvent("status", {
        job_id: jobId,
        status: "ready",
      }),
    ].join("");

    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody,
      headers: {
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  });

  await page.route(`**/api/ai-jobs/${jobId}/apply`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "applied",
        suggestion_id: suggestionId,
      }),
    });
  });

  await page.getByRole("button", { name: /^Run Rewrite$/ }).click();

  await expect(page.getByRole("heading", { name: /^Suggestion$/ })).toBeVisible();
  await page.getByRole("tab", { name: /^Edit$/ }).click();
  await expect(page.locator("#ai-edit-textarea")).toHaveValue(acceptedText);

  await page.getByRole("button", { name: /^Accept$/ }).click();

  await expect(page.locator(".ai-undo-banner")).toContainText("Suggestion applied");
  await expect(page.locator(".ai-suggestion")).toBeHidden();
  await expect(editor).toContainText(acceptedText);

  const documentUrl = page.url();
  const storageState = await page.context().storageState();
  const freshContext = await browser.newContext({ storageState });
  const freshPage = await freshContext.newPage();

  await freshPage.goto(documentUrl);
  await expect(freshPage.getByText("Connected")).toBeVisible({ timeout: 15_000 });
  await expect(freshPage.locator(".ProseMirror").first()).toContainText(acceptedText, {
    timeout: 15_000,
  });

  await freshContext.close();
});
