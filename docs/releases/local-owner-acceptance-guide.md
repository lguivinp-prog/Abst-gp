# Abast-gp Local Owner Acceptance Guide

Esta guía permite a un usuario no técnico probar la funcionalidad E2E local del producto Abast-gp.

## 1. Cómo Iniciar
Haga doble clic en el archivo `start-abast.ps1` en la carpeta raíz del proyecto. Este script levantará automáticamente todos los contenedores necesarios en Docker.

## 2. Qué URL Abrir
Abra su navegador y visite: `http://localhost:8080`.

## 3. Inicio de Sesión
Use las credenciales preconfiguradas:
- Para rol completo: Username `supervisor`, Password `supervisor`.
- Para rol limitado: Username `operator`, Password `operator`.

## 4. Crear Expediente y Cargar PDF
Una vez dentro, haga clic en `+ Create Expediente`. Luego haga clic en `Open`. Use el botón `Upload PDF` en el Paso 1 para simular la carga. El sistema extraerá inmediatamente requisitos a la Matriz.

## 5. Decisiones de Negocio
Siga el workflow numerado de izquierda a derecha. Valide los requisitos, agregue proveedores y por último, en el Paso 4, haga clic en `Approve` (solo funcionará si ingresó como supervisor). 

## 6. Cerrar el Sistema
Haga doble clic en `stop-abast.ps1` para apagar todo. Sus datos se conservarán en los volúmenes para la siguiente vez que ejecute el `start`.
