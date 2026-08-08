# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: sre_monitoring.spec.ts >> Fase 6.5 — React 19 SRE Monitoring Dashboard E2E >> ADMIN puede acceder a Monitoreo SRE y visualizar telemetría completa
- Location: tests/sre_monitoring.spec.ts:8:7

# Error details

```
Test timeout of 120000ms exceeded.
```

```
Error: locator.click: Test timeout of 120000ms exceeded.
Call log:
  - waiting for locator('a[href="/monitoring"]')
    - locator resolved to <a class="nav-item " href="/monitoring">…</a>
  - attempting click action
    - waiting for element to be visible, enabled and stable
  - element was detached from the DOM, retrying

```

# Page snapshot

```yaml
- generic [ref=f1e4]:
  - generic [ref=f1e5]:
    - heading "Abst-gp V5.0" [level=1] [ref=f1e6]
    - paragraph [ref=f1e7]: Inicia sesión para continuar
  - generic [ref=f1e8]:
    - generic [ref=f1e9]:
      - generic [ref=f1e10]: Usuario
      - textbox "Usuario" [ref=f1e11]
    - generic [ref=f1e12]:
      - generic [ref=f1e13]: Contraseña
      - textbox "Contraseña" [ref=f1e14]
    - button "Ingresar" [disabled] [ref=f1e15]
```

# Test source

```ts
  67  |             p99_ms: 8500.0,
  68  |             avg_ms: 1800.0,
  69  |             min_ms: 300.0,
  70  |             max_ms: 9200.0,
  71  |           },
  72  |           metrics_by_job_type: [
  73  |             {
  74  |               job_type: 'QUOTATION_EXTRACTION',
  75  |               sample_count: 100,
  76  |               p50_ms: 1100.0,
  77  |               p95_ms: 3900.0,
  78  |               p99_ms: 6000.0,
  79  |               avg_ms: 1450.0,
  80  |               min_ms: 300.0,
  81  |               max_ms: 7000.0,
  82  |             },
  83  |           ],
  84  |           timestamp: new Date().toISOString(),
  85  |         },
  86  |       });
  87  |     });
  88  | 
  89  |     await page.route('**/admin/monitoring/errors*', async (route) => {
  90  |       await route.fulfill({
  91  |         json: {
  92  |           time_window_hours: 24,
  93  |           tenant_id: 'tenant-demo',
  94  |           total_processed: 200,
  95  |           failed_jobs: 4,
  96  |           failure_rate_percent: 2.0,
  97  |           errors_by_category: {
  98  |             TRANSIENT_INFRA: 3,
  99  |             CORRUPT_INPUT: 1,
  100 |           },
  101 |           errors_by_code: {
  102 |             REDIS_CONNECTION_TIMEOUT: 3,
  103 |             CORRUPT_PDF_FILE: 1,
  104 |           },
  105 |           errors_by_job_type: {
  106 |             QUOTATION_EXTRACTION: 3,
  107 |             OCR_PROCESSING: 1,
  108 |           },
  109 |           timestamp: new Date().toISOString(),
  110 |         },
  111 |       });
  112 |     });
  113 | 
  114 |     await page.route('**/admin/monitoring/recovery', async (route) => {
  115 |       await route.fulfill({
  116 |         json: {
  117 |           stale_processing_count: 1,
  118 |           stale_queued_count: 0,
  119 |           recovered_jobs_count: 5,
  120 |           failed_final_count: 1,
  121 |           last_execution: new Date().toISOString(),
  122 |           stale_processing_jobs: [
  123 |             {
  124 |               job_id: 'job-orphan-999',
  125 |               job_type: 'QUOTATION_EXTRACTION',
  126 |               status: 'PROCESSING',
  127 |               attempt_count: 1,
  128 |               max_retries: 3,
  129 |               created_at: new Date(Date.now() - 60000).toISOString(),
  130 |               started_at: new Date(Date.now() - 55000).toISOString(),
  131 |               last_heartbeat_at: new Date(Date.now() - 45000).toISOString(),
  132 |               stale_duration_sec: 45.0,
  133 |             },
  134 |           ],
  135 |           stale_queued_jobs: [],
  136 |         },
  137 |       });
  138 |     });
  139 | 
  140 |     await page.route('**/admin/monitoring/recovery/trigger', async (route) => {
  141 |       await route.fulfill({
  142 |         json: {
  143 |           message: 'Reconciliation cycle completed successfully',
  144 |           total_scanned: 1,
  145 |           stale_processing_count: 1,
  146 |           stale_queued_count: 0,
  147 |           recovered_retried: 1,
  148 |           marked_failed_final: 0,
  149 |           marked_failed_max_retries: 0,
  150 |           skipped_terminal: 0,
  151 |           job_details: [{ job_id: 'job-orphan-999', outcome: 'RECOVERED_RETRY' }],
  152 |           timestamp: new Date().toISOString(),
  153 |           tenant_id: 'tenant-demo',
  154 |         },
  155 |       });
  156 |     });
  157 | 
  158 |     // Iniciar sesión
  159 |     await page.goto('/');
  160 |     await page.fill('input[name="username"]', 'admin');
  161 |     await page.fill('input[name="password"]', 'adminpassword');
  162 |     await page.click('button[type="submit"]');
  163 | 
  164 |     // Verificar enlace en sidebar
  165 |     const monitoringNav = page.locator('a[href="/monitoring"]');
  166 |     await expect(monitoringNav).toBeVisible({ timeout: 10000 });
> 167 |     await monitoringNav.click();
      |                         ^ Error: locator.click: Test timeout of 120000ms exceeded.
  168 | 
  169 |     // 1. Header y Breadcrumbs
  170 |     await expect(page.locator('h1:has-text("Centro de Observabilidad & SRE")')).toBeVisible();
  171 |     await expect(page.locator('.breadcrumb:has-text("Administración / Monitoreo & SRE")')).toBeVisible();
  172 | 
  173 |     // 2. Salud del Cluster de Workers
  174 |     await expect(page.locator('h3:has-text("Estado del Clúster de Workers")')).toBeVisible();
  175 |     await expect(page.locator('text=quotation-worker-1')).toBeVisible();
  176 | 
  177 |     // 3. Métricas de Rendimiento & SLAs
  178 |     await expect(page.locator('h3:has-text("Métricas de Rendimiento & SLAs")')).toBeVisible();
  179 |     await expect(page.locator('span.kpi-label:has-text("p50 (Mediana)")')).toBeVisible();
  180 |     await expect(page.locator('span.kpi-label:has-text("p95 (SLA Crítico)")')).toBeVisible();
  181 | 
  182 |     // 4. Taxonomía de Errores
  183 |     await expect(page.locator('h3:has-text("Taxonomía & Matriz de Errores V5.4")')).toBeVisible();
  184 |     await expect(page.locator('text=TRANSIENT_INFRA')).toBeVisible();
  185 | 
  186 |     // 5. Panel de Resiliencia y Recuperación
  187 |     await expect(page.locator('h3:has-text("Panel de Resiliencia & Recuperación Automática")')).toBeVisible();
  188 |     await expect(page.locator('text=job-orphan-999')).toBeVisible();
  189 | 
  190 |     // 6. Ejecución de Reconciliación Manual
  191 |     const triggerBtn = page.locator('button:has-text("Ejecutar Reconciliación Manual")');
  192 |     await expect(triggerBtn).toBeVisible();
  193 |     await triggerBtn.click();
  194 | 
  195 |     // Confirmar en Modal
  196 |     await expect(page.locator('.sre-modal h3:has-text("Confirmar Reconciliación de Jobs")')).toBeVisible();
  197 |     await page.click('button:has-text("Confirmar y Ejecutar")');
  198 | 
  199 |     // Verificar banner de resultado
  200 |     await expect(page.locator('text=Reconciliación Ejecutada: Reconciliation cycle completed successfully')).toBeVisible({ timeout: 10000 });
  201 |   });
  202 | 
  203 |   test('OPERATOR no tiene acceso al enlace de Monitoreo SRE en sidebar', async ({ page }) => {
  204 |     await page.route('**/auth/token', async (route) => {
  205 |       await route.fulfill({
  206 |         json: { access_token: OPERATOR_TOKEN, token_type: 'bearer', role: 'OPERATOR' },
  207 |       });
  208 |     });
  209 |     await page.route('**/cases/', async (route) => {
  210 |       if (route.request().resourceType() === 'document') {
  211 |         return route.continue();
  212 |       }
  213 |       await route.fulfill({ json: [] });
  214 |     });
  215 | 
  216 |     await page.goto('/');
  217 |     await page.fill('input[name="username"]', 'operator');
  218 |     await page.fill('input[name="password"]', 'operatorpass');
  219 |     await page.click('button[type="submit"]');
  220 | 
  221 |     await expect(page.locator('a[href="/cases"]')).toBeVisible({ timeout: 10000 });
  222 |     await expect(page.locator('a[href="/monitoring"]')).not.toBeVisible();
  223 |   });
  224 | });
  225 | 
```