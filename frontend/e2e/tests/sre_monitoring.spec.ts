import { test, expect } from '@playwright/test';

const ADMIN_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJBRE1JTiIsImV4cCI6MjAwMDAwMDAwMH0.signature';
const OPERATOR_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjAwMDAwMDAwMH0.signature';

test.describe('Fase 6.5 — React 19 SRE Monitoring Dashboard E2E', () => {

  test('ADMIN puede acceder a Monitoreo SRE y visualizar telemetría completa', async ({ page }) => {
    // Mock endpoints de monitoreo SRE
    await page.route('**/auth/token', async (route) => {
      await route.fulfill({
        json: { access_token: ADMIN_TOKEN, token_type: 'bearer', role: 'ADMIN' },
      });
    });

    await page.route('**/admin/monitoring/workers', async (route) => {
      await route.fulfill({
        json: {
          total_workers: 3,
          active_workers: 2,
          unresponsive_workers: 1,
          offline_workers: 0,
          workers: [
            {
              worker_name: 'quotation-worker-1',
              worker_type: 'quotation_worker',
              hostname: 'node-1',
              status: 'BUSY',
              current_job_id: 'job-quot-1234',
              tenant_id: 'tenant-demo',
              last_seen: new Date().toISOString(),
              started_at: new Date(Date.now() - 3600000).toISOString(),
              is_healthy: true,
              seconds_since_last_seen: 4.5,
              uptime_seconds: 3600,
            },
            {
              worker_name: 'ocr-worker-1',
              worker_type: 'ocr_worker',
              hostname: 'node-2',
              status: 'IDLE',
              current_job_id: null,
              tenant_id: 'tenant-demo',
              last_seen: new Date().toISOString(),
              started_at: new Date(Date.now() - 7200000).toISOString(),
              is_healthy: true,
              seconds_since_last_seen: 2.1,
              uptime_seconds: 7200,
            },
          ],
          timestamp: new Date().toISOString(),
        },
      });
    });

    await page.route('**/admin/monitoring/latencies*', async (route) => {
      await route.fulfill({
        json: {
          time_window_hours: 24,
          tenant_id: 'tenant-demo',
          total_samples: 150,
          global_metrics: {
            job_type: 'GLOBAL',
            sample_count: 150,
            p50_ms: 1200.0,
            p95_ms: 4500.0,
            p99_ms: 8500.0,
            avg_ms: 1800.0,
            min_ms: 300.0,
            max_ms: 9200.0,
          },
          metrics_by_job_type: [
            {
              job_type: 'QUOTATION_EXTRACTION',
              sample_count: 100,
              p50_ms: 1100.0,
              p95_ms: 3900.0,
              p99_ms: 6000.0,
              avg_ms: 1450.0,
              min_ms: 300.0,
              max_ms: 7000.0,
            },
          ],
          timestamp: new Date().toISOString(),
        },
      });
    });

    await page.route('**/admin/monitoring/errors*', async (route) => {
      await route.fulfill({
        json: {
          time_window_hours: 24,
          tenant_id: 'tenant-demo',
          total_processed: 200,
          failed_jobs: 4,
          failure_rate_percent: 2.0,
          errors_by_category: {
            TRANSIENT_INFRA: 3,
            CORRUPT_INPUT: 1,
          },
          errors_by_code: {
            REDIS_CONNECTION_TIMEOUT: 3,
            CORRUPT_PDF_FILE: 1,
          },
          errors_by_job_type: {
            QUOTATION_EXTRACTION: 3,
            OCR_PROCESSING: 1,
          },
          timestamp: new Date().toISOString(),
        },
      });
    });

    await page.route('**/admin/monitoring/recovery', async (route) => {
      await route.fulfill({
        json: {
          stale_processing_count: 1,
          stale_queued_count: 0,
          recovered_jobs_count: 5,
          failed_final_count: 1,
          last_execution: new Date().toISOString(),
          stale_processing_jobs: [
            {
              job_id: 'job-orphan-999',
              job_type: 'QUOTATION_EXTRACTION',
              status: 'PROCESSING',
              attempt_count: 1,
              max_retries: 3,
              created_at: new Date(Date.now() - 60000).toISOString(),
              started_at: new Date(Date.now() - 55000).toISOString(),
              last_heartbeat_at: new Date(Date.now() - 45000).toISOString(),
              stale_duration_sec: 45.0,
            },
          ],
          stale_queued_jobs: [],
        },
      });
    });

    await page.route('**/admin/monitoring/recovery/trigger', async (route) => {
      await route.fulfill({
        json: {
          message: 'Reconciliation cycle completed successfully',
          total_scanned: 1,
          stale_processing_count: 1,
          stale_queued_count: 0,
          recovered_retried: 1,
          marked_failed_final: 0,
          marked_failed_max_retries: 0,
          skipped_terminal: 0,
          job_details: [{ job_id: 'job-orphan-999', outcome: 'RECOVERED_RETRY' }],
          timestamp: new Date().toISOString(),
          tenant_id: 'tenant-demo',
        },
      });
    });

    // Iniciar sesión
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');

    // Verificar enlace en sidebar
    const monitoringNav = page.locator('a[href="/monitoring"]');
    await expect(monitoringNav).toBeVisible({ timeout: 10000 });
    await monitoringNav.click();

    // 1. Header y Breadcrumbs
    await expect(page.locator('h1:has-text("Centro de Observabilidad & SRE")')).toBeVisible();
    await expect(page.locator('.breadcrumb:has-text("Administración / Monitoreo & SRE")')).toBeVisible();

    // 2. Salud del Cluster de Workers
    await expect(page.locator('h3:has-text("Estado del Clúster de Workers")')).toBeVisible();
    await expect(page.locator('text=quotation-worker-1')).toBeVisible();

    // 3. Métricas de Rendimiento & SLAs
    await expect(page.locator('h3:has-text("Métricas de Rendimiento & SLAs")')).toBeVisible();
    await expect(page.locator('span.kpi-label:has-text("p50 (Mediana)")')).toBeVisible();
    await expect(page.locator('span.kpi-label:has-text("p95 (SLA Crítico)")')).toBeVisible();

    // 4. Taxonomía de Errores
    await expect(page.locator('h3:has-text("Taxonomía & Matriz de Errores V5.4")')).toBeVisible();
    await expect(page.locator('text=TRANSIENT_INFRA')).toBeVisible();

    // 5. Panel de Resiliencia y Recuperación
    await expect(page.locator('h3:has-text("Panel de Resiliencia & Recuperación Automática")')).toBeVisible();
    await expect(page.locator('text=job-orphan-999')).toBeVisible();

    // 6. Ejecución de Reconciliación Manual
    const triggerBtn = page.locator('button:has-text("Ejecutar Reconciliación Manual")');
    await expect(triggerBtn).toBeVisible();
    await triggerBtn.click();

    // Confirmar en Modal
    await expect(page.locator('.sre-modal h3:has-text("Confirmar Reconciliación de Jobs")')).toBeVisible();
    await page.click('button:has-text("Confirmar y Ejecutar")');

    // Verificar banner de resultado
    await expect(page.locator('text=Reconciliación Ejecutada: Reconciliation cycle completed successfully')).toBeVisible({ timeout: 10000 });
  });

  test('OPERATOR no tiene acceso al enlace de Monitoreo SRE en sidebar', async ({ page }) => {
    await page.route('**/auth/token', async (route) => {
      await route.fulfill({
        json: { access_token: OPERATOR_TOKEN, token_type: 'bearer', role: 'OPERATOR' },
      });
    });
    await page.route('**/cases/', async (route) => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      await route.fulfill({ json: [] });
    });

    await page.goto('/');
    await page.fill('input[name="username"]', 'operator');
    await page.fill('input[name="password"]', 'operatorpass');
    await page.click('button[type="submit"]');

    await expect(page.locator('a[href="/cases"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('a[href="/monitoring"]')).not.toBeVisible();
  });
});
