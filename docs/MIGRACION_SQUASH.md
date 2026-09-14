# Resumen de Squash de Migraciones

## Migraciones y Semillas (Seeds) Descartadas
1. **Semillas Antiguas Incompatibles**: No se encontraron semillas masivas (como el catálogo CIIU completo) en el historial de Alembic, sino inserciones aisladas (mega_tenant, system_settings) que fueron convertidas al nuevo `scripts/seed_base.py`.
2. Las inserciones sobre `quarantine_manifest` o similares que se hacían a nivel de datos (durante migraciones de tipo data-migration) han sido descartadas por apuntar a tablas/esquemas puramente transaccionales que inician vacías en este despliegue on-premise.

## Deuda Técnica Registrada (No Desarrollada)
La capa multi-tenant, el capacity governor, la telemetría institucional y el rollout por tenant forman parte del alcance actual. Estos componentes cuentan con cobertura automatizada en los módulos correspondientes y la recuperación ante desastres se valida mediante los gates de `verification/dr`. La documentación operativa debe mantenerse alineada con cada release.
