import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: 0,
  reporter: [
    ['json', { outputFile: 'report.json' }],
    ['list'],
  ],
  use: {
    headless: true,
  },
});
