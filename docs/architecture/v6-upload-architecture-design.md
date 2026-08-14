# V6.0 Upload Architecture Design (Object Storage)

## 1. Flujo Actual (Backend Upload + Filesystem)
Actualmente (V5.5), el frontend envía archivos a través de un `multipart/form-data` al endpoint síncrono `/documents/upload`.
- El backend consume los bytes utilizando `SpooledTemporaryFile`.
- El backend (FastAPI) orquesta la lectura, cálculo criptográfico (SHA-256) y lo escribe al disco local POSIX (ej. `settings.UPLOADS_DIR/tenant_id/doc_id.pdf`).
- Esto satura el ancho de banda del backend, bloquea los HTTP workers y genera errores de OOM (Out of Memory) o Timeouts en cargas superiores a 100MB.

## 2. Flujo Objetivo (Direct Object Storage Upload)
Para escalar a V6, la carga de datos masivos se cede al cliente.
1. **Initiate Upload**: El Frontend solicita intención de subir un archivo.
2. **Presigned URL**: El Backend autoriza y retorna una o múltiples URLs firmadas (Presigned URLs) que apuntan directamente a S3/MinIO.
3. **Multipart Upload (Client-Side)**: El Frontend sube los *chunks* binarios directamente al Object Storage.
4. **Complete Upload**: El Frontend notifica al Backend que los *chunks* finalizaron, incluyendo el cálculo SHA-256 definitivo que fue computado localmente en el navegador.

## 3. Contratos API

### `POST /v2/documents/upload/initiate`
- **Request Body**:
  ```json
  {
    "filename": "informe_financiero_2026.pdf",
    "content_type": "application/pdf",
    "size_bytes": 104857600
  }
  ```
- **Response**:
  ```json
  {
    "upload_id": "minio-upload-hash-id",
    "document_id": "uuid-v4",
    "presigned_urls": [
      { "part_number": 1, "url": "https://s3.../part1?signature=..." }
    ],
    "expires_in": 3600
  }
  ```

### `POST /v2/documents/upload/complete`
- **Request Body**:
  ```json
  {
    "document_id": "uuid-v4",
    "upload_id": "minio-upload-hash-id",
    "sha256_checksum": "a8f5f167f44f...",
    "parts": [
      { "part_number": 1, "etag": "etag-chunk-1" }
    ]
  }
  ```
- **Response**:
  ```json
  {
    "status": "VALIDATING",
    "message": "Upload marked for verification."
  }
  ```

## 4. Seguridad

- **Tenant Validation**: Las firmas (Presigned URLs) inyectarán en la ruta el prefijo inmutable `/{tenant_id}/{document_id}` de modo que ningún usuario cruce datos entre organizaciones (Data Isolation).
- **Checksum Authority**: S3/MinIO inyectará el `sha256_checksum` en su Metadata como Source of Truth (SSOT).
- **Size Limits**: El API `initiate` rechazará intenciones superiores al límite configurado (Ej. >500MB) y S3 validará internamente vía firmas la cuota de la solicitud.
- **Expiration**: Todas las URLs caducan estrictamente en 60 minutos (3600s), mitigando ataques de suplantación.
- **CORS**: El bucket de S3/MinIO deberá tener cabeceras `Access-Control-Allow-Origin` permitiendo a los dominios del frontend empujar binarios (`PUT`).

## 5. Estados del Documento

Se transiciona desde un modelo de inserción síncrona a una máquina de estados (FSM):
1. **`UPLOADING`**: Se generó el Intento, el cliente sube chunks pero S3 aún no consolida.
2. **`UPLOADED`**: Cliente notificó Complete; S3 unió las partes, pero el backend aún debe auditar internamente.
3. **`VALIDATING`**: Un worker asíncrono o rutina sincrona verifica que el tamaño reportado y checksum sean fieles a S3 (Antivirus hook).
4. **`AVAILABLE`**: Archivo sano, listo para ser orquestado hacia OCR (`ProcessingJob`).
5. **`FAILED`**: Corrupción de firma, timeout en la subida o error en OCR.

## 6. Auditoría
Cada transición de estado emitirá una traza inmutable en `JobRepository` (audit log), rastreando tiempos (upload lag) y caídas de transferencia, fortaleciendo el marco SRE de la V5.6.

## 7. Compatibilidad DR V5.5
Este diseño arquitectónico es complementario (Side-by-Side). Durante la fase beta de V6, el endpoint legado `/documents/upload` que inyecta en estado `AVAILABLE` de un golpe, seguirá siendo la autoridad (DR 15 PASS), permitiendo que la nueva familia `/v2` nazca bajo Feature Flags. No requerirá migrar el esquema SQL base que audita DR.
