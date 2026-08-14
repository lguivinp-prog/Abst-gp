# V6 Upload Cleanup Architecture Design

## 1. Overview
El rediseño del flujo de subida documental (Upload V2) hacia un modelo híbrido con Object Storage (S3/MinIO) introduce estados asíncronos y transferencias directas desde el cliente. Esto presenta nuevos desafíos operativos: subidas interrumpidas, archivos huérfanos y fragmentos de *Multipart Uploads* abandonados.

Este documento define la arquitectura de limpieza (Cleanup Architecture) requerida para garantizar que el almacenamiento no se degrade con el tiempo y asegurar consistencia con la base de datos PostgreSQL.

## 2. Problem Statement
En el flujo Upload V2:
1. **Initiate**: El backend registra el documento en estado `UPLOADING` y genera una URL firmada.
2. **Upload**: El frontend envía el binario (o los fragmentos multipart) directamente a S3.
3. **Complete**: El frontend notifica al backend, el cual valida y pasa el documento a `AVAILABLE`.

**Modos de Fallo:**
- El cliente cierra la pestaña durante el paso 2. El estado queda perpetuamente en `UPLOADING`.
- El cliente inicia una subida *Multipart*, sube 3 de 10 partes, y se desconecta. S3 retiene las 3 partes invisibles cobrando almacenamiento.
- Un error de validación (ej. Checksum mismatch) deja un objeto basura en S3 en estado `FAILED`.

## 3. Storage Lifecycle Rules (S3 Native)

La primera línea de defensa debe ser nativa del Object Storage para evitar dependencias exclusivas en el backend.

### 3.1 Abort Incomplete Multipart Uploads
Se debe configurar una regla en el bucket S3 para eliminar automáticamente cualquier *Multipart Upload* que no haya concluido en un plazo de `24 horas`.

```xml
<LifecycleConfiguration>
  <Rule>
    <ID>AbortIncompleteMultipartUploads</ID>
    <Status>Enabled</Status>
    <AbortIncompleteMultipartUpload>
      <DaysAfterInitiation>1</DaysAfterInitiation>
    </AbortIncompleteMultipartUpload>
  </Rule>
</LifecycleConfiguration>
```

### 3.2 Temp Prefix Expiration
Para evitar desincronizaciones, los objetos físicos podrían escribirse inicialmente en un prefijo `uploads/tmp/` y, una vez confirmados en `/complete`, ser copiados (o etiquetados) a `uploads/tenant_id/`. Los objetos en `tmp/` pueden expirar automáticamente en 24 horas usando una regla S3 nativa. Sin embargo, para minimizar llamadas API, Abst-GP utilizará conciliación desde el Backend.

## 4. Backend Reconciliation Strategy

### 4.1 Estado `EXPIRED`
Se introduce el estado `EXPIRED` en el flujo documental (FSM). 
Si un documento permanece en estado `UPLOADING` por más de `24 horas`, se considerará expirado y no se admitirá su conclusión.

### 4.2 Tarea Celery: `cleanup_abandoned_uploads_task`
Un *CronJob* periódico (ej. cada noche a las 03:00 AM) ejecutará un Worker dedicado a la conciliación.

**Flujo del Worker:**
1. Consultar PostgreSQL por todos los `UploadedDocument` con estado `UPLOADING` o `VALIDATING` y `created_at < (NOW() - 24 HOURS)`.
2. Para cada registro:
   - Marcar el estado en BD como `EXPIRED`.
   - Instruir al `ObjectStorageAdapter` para que haga `delete(stored_path)`. Si el objeto no existe (nunca subió), se ignora el error.
3. Consultar PostgreSQL por documentos en estado `FAILED` (error en `/complete`).
   - Eliminar el binario asociado en S3.

## 5. Security & DR Impact

- **Disaster Recovery (DR)**: La limpieza garantiza que los respaldos lógicos (PostgreSQL) y físicos (S3) no contengan referencias desincronizadas. Durante una restauración PITR, si se recupera un estado `UPLOADING`, el Cleanup Worker lo podará eventualmente.
- **Tenant Isolation**: La eliminación física no debe cruzar fronteras lógicas; los `stored_path` mantendrán el prefijo `tenant_id/`.

## 6. Próximos Pasos
- Configurar Lifecycle Rules en el clúster productivo de MinIO (Terraform o CLI).
- Implementar la tarea asíncrona `cleanup_abandoned_uploads_task` en `worker/tasks.py`.
