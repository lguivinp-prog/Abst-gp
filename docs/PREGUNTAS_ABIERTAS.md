# Preguntas Abiertas Críticas

Las siguientes preguntas estratégicas no pueden ser respondidas mediante la mera inspección del código fuente y requieren confirmación del dueño del proyecto.

### 1. Despliegue de Motores OCR (Tesseract / Ghostscript)
**Pregunta:** El sistema depende altamente de `ocrmypdf` y `pdfplumber`, lo que requiere instalar dependencias a nivel de sistema operativo que son conflictivas y pesadas. Dado que hay una restricción estricta de no usar AWS (ej. Textract), ¿se asumirá que el host (o el clúster on-premise) proveerá estas dependencias nativas instaladas a medida, o deben empaquetarse masivamente en el contenedor de backend?
* **Opción por defecto:** Empaquetar todas las dependencias en el Dockerfile del Backend.
* **Consecuencia:** La imagen del backend crecerá considerablemente (> 1.5GB) y consumirá un alto nivel de RAM por hilo de ejecución, requiriendo nodos más grandes.

### 2. Estado de la Migración a la Versión 6
**Pregunta:** Existe un solapamiento masivo de archivos untracked (v6) y referencias truncadas al código previo (v5) que rompen la aplicación. ¿El objetivo de esta fase es estabilizar el código legacy (V5.5) y abandonar la migración, o debemos forzar la culminación de la reestructuración a V6 cortando los lazos viejos?
* **Opción por defecto:** Forzar la finalización de V6 (Forward-fix). Borrar/depurar referencias muertas a módulos de V5.
* **Consecuencia:** Se perderá la compatibilidad hacia atrás y los clientes locales de V5.5 dejarán de funcionar si se despliega este branch; demandará resolver de golpe todas las migraciones rotas de Alembic.

### 3. Modelo de Seguridad y Secretos
**Pregunta:** El repositorio expone contraseñas y claves genéricas en el archivo `.env.example` y existe documentación apuntando hacia implementaciones aisladas on-premise. ¿Cómo se espera inyectar secretos y configuraciones (como `DATABASE_URL`) en los despliegues finales de cliente? ¿Usarán Helm charts, archivos locales administrados por DevOps o vaults?
* **Opción por defecto:** Exigir un archivo `.env` estricto proveído manualmente mediante volúmenes o variables de entorno del orquestador.
* **Consecuencia:** Mayor fricción durante las pruebas locales y el onboarding de desarrollo, pero se blinda la seguridad al evitar secrets en el repositorio.

### 4. Tolerancia del Motor OCR (Human in the Loop)
**Pregunta:** El ajuste de `intersection_y_tolerance = 3` en `engine.py` soluciona los problemas de fusión de tablas para los PDFs de muestra de "Materiales de Oficina", pero puede causar que otras tablas con filas irregulares se fragmenten demasiado. Si esto ocurre, ¿se espera que el usuario final corrija la extracción manualmente en la UI, o el OCR debe ser infalible?
* **Opción por defecto:** Habilitar una interfaz de usuario (UI) para validación manual y edición de tablas post-extracción.
* **Consecuencia:** Aumenta el alcance de desarrollo del frontend ("SectionEditor.tsx"), añadiendo complejidad, pero mitigando la inevitabilidad de los errores del OCR.
