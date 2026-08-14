# V6.1 Retirement Plan

**Date:** 2026-08-09
**Status:** DRAFT (Awaiting Wave 5 Completion)

## Objetivo
Desactivar formalmente y de manera segura la infraestructura base (V6.1), incluyendo los nodos de Memoria (FAISS) y las APIs obsoletas.

## Criterios de Aprobación (Pre-requisitos)
El retiro de V6.1 está estrictamente condicionado por:
1. **100% Migración:** El *Rollout Controller* debe haber completado la *Wave 5* con el 100% del tráfico despachado por pgvector.
2. **Estabilidad:** Mínimo de 30 días operando en Wave 5 sin incidentes de latencia P95 > 20ms ni caídas del *Vector Service*.
3. **Ausencia de Rollback:** 0% de *Tenant Rollbacks* durante la etapa final.
4. **Respaldo Completado:** Se debe generar un snapshot lógico y en frío del índice FAISS de todos los clientes.

## Fases de Retiro
1. **Congelamiento (Code Freeze):**
   - V6.1 se declara obsoleto. No se admiten nuevas funcionalidades ni fixes no-críticos.
2. **Backups & Destrucción (Golden Image):**
   - Todos los snapshots `.faiss` en disco se exportarán a AWS S3 Glacier (Cold Storage) con retención de 1 año.
3. **Desactivación de Nodos (Scale-to-Zero):**
   - Los deployments EKS correspondientes a los indexadores FAISS legacy se escalarán a 0 réplicas.
   - El estado del *EngineRouter* transicionará a un modo de operación permanente.
4. **Clientes Pendientes:**
   - Si por restricciones legales o técnicas un cliente *Excluded* debe mantenerse, se desplegará una pila dedicada (Tenant-Specific Legacy Stack) a un costo premium.

## Fecha Estimada de Retiro
T+90 días a partir de la estabilización certificada del Rollout Wave 5.
