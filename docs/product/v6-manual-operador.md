# Abast-gp V6 - Manual del Operador (Especialista)

## 1. Carga de Documentos (Gate)
- Al subir el Anexo 3 (Contratos), espere unos segundos. 
- Si aparece un cuadro rojo de "Calidad Pobre (BLOCKED)", el sistema rechaza el PDF. Cancele, vaya al escáner físico y aumente la resolución a 300 DPI. No intente saltarse este paso, el OCR no leerá sus contratos.

## 2. Evaluación Asistida (RAG)
- El sistema leerá el texto y le sugerirá montos y rubros automáticamente.
- **Su trabajo es revisar, no asentir a ciegas.** 
- Si el monto extraído por la máquina está mal o pertenece a otro postor, presione `[ EDITAR ]`, escriba la cifra correcta, justifique y guarde.
- Si está correcto, presione `[ VALIDAR ]`.

## 3. Fallas del Sistema Externo
- Si la máquina indica `MANUAL_REQUIRED` en la sección RNP/SUNAT, significa que la API del gobierno está colgada. Usted deberá descargar el PDF manual de los portales del Estado y adjuntarlo en la ficha del postor para continuar su trabajo.
