import { test, expect } from '@playwright/test';

// A real browser test (not just synchronous assertions) so the demo proves
// this is genuinely a Playwright run, not just JS unit tests wearing a
// Playwright reporter. Uses setContent instead of a live server/URL to keep
// the CI job self-contained -- no app to stand up first.

test('renders the demo page heading', async ({ page }) => {
  await page.setContent('<html><body><h1>Notifications Dashboard</h1></body></html>');
  await expect(page.locator('h1')).toHaveText('Notifications Dashboard');
});
