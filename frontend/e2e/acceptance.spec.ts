import { test, expect } from '@playwright/test';

test('E2E Abast-gp Local Owner Acceptance', async ({ page }) => {
  // LOGIN
  await page.goto('http://localhost:8080');
  await page.fill('input[placeholder="Username"]', 'supervisor');
  await page.fill('input[placeholder="Password"]', 'supervisor');
  await page.click('button:has-text("Login")');

  // CREATE EXPEDIENT
  await page.click('button:has-text("+ Create Expediente")');
  await page.waitForSelector('text=New Expediente');
  await page.click('button:has-text("Open")');

  // UPLOAD REAL PDF (Simulated in UI but triggers multipart)
  await page.click('button:has-text("Upload PDF")');
  
  // WAIT PROCESSING / MANUAL FALLBACK
  // ... (UI triggers manual fallback or shows processing)
  
  // VALIDATE REQUIREMENTS
  await page.click('button:has-text("Validate All")');

  // ADD SUPPLIERS & QUOTATIONS (Step 3)
  await page.click('button:has-text("Add Supplier")');
  
  // RECORD DECISION (SUPERVISOR)
  await page.click('button:has-text("Approve")');
  
  // GENERATE OUTPUT
  await page.click('button:has-text("Generate Contract Preview")');
  
  // Verify output
  expect(await page.content()).toContain('Approved');
});
