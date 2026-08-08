# POLÍTICA DE RETENCIÓN, RESPALDO Y GOBERNANZA DE DATOS (BACKUP RETENTION POLICY)

**Plataforma**: Abst-gp / Document Intelligence Pipeline  
**Versión**: V5.5 Enterprise Operations  
**Clasificación**: Confidencial / Enterprise  
**Alcance**: Bases de datos PostgreSQL, Archivo WAL, Filesystem de Documentos y Auditoría  

---

## 1. PRINCIPIO 3-2-1 DE RESPALDO EMPRESARIAL

Abst-gp implementa estrictamente la regla 3-2-1 para todos los activos de información institucional:
* **3 Copias de Información**: Datos en producción (PostgreSQL + S3/Filesystem), 1 copia local de respaldo rápido (Vault Hot Tier), 1 copia remota inmutable (Vault Cold Tier).
* **2 Medios Diferentes**: Almacenamiento NVMe local de alta velocidad para WAL y dumps base, y Blob Storage Object-Lock / WORM (Write Once, Read Many).
* **1 Copia Offsite / Inmutable**: Copia externa con bloqueo de escritura y versionado inmutable a prueba de ransomware.

---

## 2. ESQUEMA DE NIVELES DE ALMACENAMIENTO Y RETENCIÓN (TIERS)

| Tier | Frecuencia de Captura | Período de Retención | Tipo de Almacenamiento | RTO Objetivo |
| :--- | :--- | :--- | :--- | :--- |
| **Hot Tier (Local)** | Continuo (WAL Archive $\le$ 60s) + Base Backup diario | 7 Días | NVMe SSD cifrado (AES-256) | $\le$ 5 min |
| **Warm Tier (Nearline)** | Base Backup semanal + Catálogo de Checksums | 30 Días | Object Storage Standard cifrado | $\le$ 15 min |
| **Cold Tier (Long-term Archive)** | Consolidado mensual con manifiesto firmado | 365 Días (1 Año) / 5 Años regulatorio | Object Storage Glacier / WORM Inmutable | $\le$ 2 horas |

---

## 3. ESPECIFICACIÓN TÉCNICA DEL MANIFIESTO Y METADATOS

Cada paquete de backup debe incluir un archivo `backup-manifest.json` que detalle:
1. `backup_id`: Identificador único determinista basado en timestamp UTC.
2. `postgres_version` y `alembic_version`: Para garantizar compatibilidad estricta de esquema binario.
3. `base_backup`: Nombre de archivo, tamaño en bytes, suma de verificación SHA-256, start LSN, stop LSN y timeline ID.
4. `documents_snapshot`: Archivo comprimido, suma SHA-256 y referencia a `backup-checksums.json`.
5. `wal_archive`: Lista de segmentos WAL contenidos con sus respectivas sumas SHA-256.
6. `security`: Firma HMAC-SHA256 generada con la clave criptográfica institucional. **Prohibido incluir contraseñas, secretos o credenciales en texto plano.**

---

## 4. CALENDARIO DE AUDITORÍA Y SIMULACROS DE DISASTER RECOVERY

* **Validación de Checksums Automática**: Diaria (Jobs de fondo de integridad).
* **Simulacro Automatizado de Restauración en Aislamiento**: Semanal (Pipeline CI/CD y Sandbox SRE).
* **Simulacro Integral con Intervención de Equipo SRE**: Trimestral (Verificación de RPO $\le$ 5m, RTO $\le$ 15m).
* **Auditoría de Inmutabilidad y Criptografía**: Semestral.
