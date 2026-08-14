# V6 STORAGE ABSTRACTION LAYER DESIGN

**Plataforma**: Abst-gp  
**Fase**: V6.0-B (Storage Abstraction)  
**Clasificación**: Diseño de Arquitectura de Almacenamiento  

---

## 1. ESTADO ACTUAL

En la certificación V5.5 (Enterprise DR), el ecosistema maneja los documentos (imágenes, PDFs) depositándolos directamente en un sistema de archivos local (`/data/uploads` o similar) montado como volumen en `docker-compose`.

- **Flujo de Upload**: La API recibe el binario, calcula el checksum, y escribe físicamente el archivo en el volumen usando llamadas OS nativas (`os.open`, `shutil.copyfileobj`).
- **OCR Worker**: Los workers extraen la ruta local de la base de datos (PostgreSQL) y leen el archivo asumiendo disponibilidad posix (ej. `/uploads/tenant_1/file.pdf`).
- **Checksum Handling**: Validación reactiva. Se apoya en el DR SRE Nightly job que recorre el disco y compara los hashes de archivo con los registros en PostgreSQL.

---

## 2. PROBLEMAS DEL FILESYSTEM LOCAL (HACIA CLOUD-NATIVE)

1. **Cuello de Botella de Escalabilidad Horizontal**: En un clúster Kubernetes (K8s), múltiples réplicas de `api` o `worker-ocr` en distintos nodos físicos no pueden compartir un disco estándar (`ReadWriteOnce`). Exigiría NFS (`ReadWriteMany`), el cual presenta alta latencia I/O para procesamiento de imágenes masivo.
2. **Fragilidad de Disaster Recovery**: Realizar backups de un sistema de archivos en vivo (rsync, tar) sin locking produce estados inconsistentes o requiere snapshots a nivel de bloque (EBS) que complican la restauración ágil probada en V5.5.
3. **Seguridad / Aislamiento Múltiple (Multitenancy)**: Un *path traversal vulnerability* en la API podría exponer documentos cruzados si ambos residen en el mismo volumen posix.

---

## 3. DISEÑO: STORAGE ABSTRACTION LAYER

Para desacoplar el motor físico sin romper la retrocompatibilidad con V5.5, se implementará el patrón **Adapter** / **Strategy**.

### A. `DocumentStorage` (Interface)
Se creará una clase base abstracta en Python (ej. `app/core/storage/base.py`) con un contrato estricto:
```python
class DocumentStorage(ABC):
    @abstractmethod
    def save(self, tenant_id: str, file_stream: BinaryIO, checksum: str) -> str:
        pass
    
    @abstractmethod
    def get(self, uri: str) -> BinaryIO:
        pass
        
    @abstractmethod
    def delete(self, uri: str) -> bool:
        pass
```

### B. `LocalStorageAdapter`
Implementará la interfaz utilizando I/O clásico (`os`, `pathlib`).  
**Objetivo**: Mantener el soporte total para despliegues monolíticos heredados y garantizar que la certificación **V5.5 Enterprise DR no se rompa**. Las instalaciones *On-Premise* seguirán usando este adapter.

### C. `ObjectStorageAdapter`
Implementará la interfaz utilizando S3 APIs (boto3 o abstracciones asíncronas HTTP).  
**Objetivo**: Habilitar Abst-gp V6.0 nativo de nube. Traducirá el `tenant_id` y `checksum` como metadatos S3 (Object Tags), delegando la alta disponibilidad del archivo al proveedor cloud.

---

## 4. ESTRATEGIA DE MIGRACIÓN

1. **Fase de Refactor Ciego**: Reemplazar todas las ocurrencias nativas (`open()`, `os.path`) en `DocumentService`, rutas `/uploads`, y `ProcessingJob` por la inyección de la interfaz `DocumentStorage`.
2. **Toggle de Configuración**: Introducir una variable de entorno `STORAGE_BACKEND=local` por defecto. Si el usuario declara `STORAGE_BACKEND=s3`, el Factory de la aplicación inyectará el `ObjectStorageAdapter`.
3. **Data Hydration (Opcional)**: En entornos productivos pre-existentes, se proveerá un script de migración que lea el File System local y publique cada documento hacia S3, actualizando la URI en PostgreSQL.

---

## 5. COMPATIBILIDAD V5 / V6

El diseño de abstracción garantiza el Principio Abierto/Cerrado (OCP de SOLID).  
- **Para V5.5 (Enterprise DR)**: El código subyacente que calcula los checksums y orquesta los workers seguirá siendo el mismo. El `LocalStorageAdapter` garantiza 100% de paridad con la evidencia congelada.
- **Para V6.0 (Cloud Native)**: Solo cambia el backend físico, habilitando HPA y escalado infinito.

---

## 6. IMPACTO EN DISASTER RECOVERY (DR)

### Gates Actuales (A-I)
Los Gates certificados seguirán pasando `PASS` inalterados porque el entorno de validación (`verification/docker-compose.dr.yml`) mantendrá la inyección de `STORAGE_BACKEND=local`.

### Futuro K8s DR (S3)
Al utilizar `ObjectStorageAdapter`, el DR del volumen físico desaparece del scope de la aplicación y se traslada a la SLA del proveedor Cloud (ej. replicación inter-región en S3 de AWS). 
El nuevo foco DR será asegurar que no exista desincronización entre el estado lógico de PostgreSQL y los objetos huérfanos en S3.
