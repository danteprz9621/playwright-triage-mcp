import { test, expect } from '@playwright/test';

// A genuinely different failure -- must NOT cluster with the status-code
// failures in api-status.spec.ts, even though it's also an `expect` call.

test('weekly export includes a summary section', async () => {
  const exportedSections = ['title', 'chart', 'footer'];
  expect(exportedSections).toContain('summary');
});

test('weekly export includes a title section', async () => {
  const exportedSections = ['title', 'chart', 'footer'];
  expect(exportedSections).toContain('title');
});
