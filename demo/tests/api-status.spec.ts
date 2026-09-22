import { test, expect } from '@playwright/test';

// These three tests simulate hitting three different endpoints that all
// happen to be down right now. They fail with different received status
// codes but the *same* assertion shape -- exactly the "same root cause,
// different call sites" case the triage clustering is built to catch.

function fakeStatusCode(endpoint: string): number {
  const down: Record<string, number> = {
    push: 500,
    email: 502,
    'in-app': 503,
  };
  return down[endpoint] ?? 200;
}

test('push notification endpoint returns 200', async () => {
  const status = fakeStatusCode('push');
  expect(status).toBe(200);
});

test('email notification endpoint returns 200', async () => {
  const status = fakeStatusCode('email');
  expect(status).toBe(200);
});

test('in-app notification endpoint returns 200', async () => {
  const status = fakeStatusCode('in-app');
  expect(status).toBe(200);
});
