# Abast-gp V6 - Emergency Access Policy (Break Glass)

## 1. Alcance
Esta política rige el acceso excepcional de Ingenieros L3 (`SYSTEM_ADMIN`) a los expedientes cifrados de un Tenant Institucional, superando temporalmente el "Tenant Isolation".

## 2. Incidentes P1
El acceso solo está justificado en Incidentes P1:
- Caída total del motor OCR.
- RAG crashea arrojando excepciones fatales (OOM) en la Base de Datos vectorial.
- Corrupción de datos sospechada post-despliegue.

## 3. Aprobación Acelerada
- El `SYSTEM_ADMIN` emite un ticket Jira y notifica al `ADMIN_IT_INSTITUCIONAL`.
- El Administrador local aprueba en el Dashboard, lo que genera un JWT con el Claim `BREAK_GLASS_GRANTED` para ese Tenant específico.

## 4. Expiración y Revocación Automática
- El token tiene un TTL (Time-to-Live) inamovible de **2 horas**.
- Expirado el plazo, el API devuelve HTTP 401. Para continuar, se requiere un nuevo ticket.

## 5. Post Incident Review (PIR)
- 48 horas post-incidente, Contraloría Interna audita los logs de lectura del `SYSTEM_ADMIN` para confirmar que no extrajo información clasificada ajena al `traceback` del error.
