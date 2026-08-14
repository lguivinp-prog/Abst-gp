# V6.0.1 Supervisor Analytics Export - UX Blueprint

## 1. Contexto Operativo
Los Supervisores Logísticos, Jefes de OGA y Auditores Internos requieren consolidar el estatus de las operaciones (Especialmente los bloqueos o *Riesgos HIGH*) para reportar a los Comités Semanales, sin depender de tableros de BI externos complejos.

## 2. Botón de Exportación (Dashboard Header)
Se añade un botón secundario al lado de los KPIs del Supervisor Dashboard:
`[ 📥 Exportar Operaciones (CSV) ]`

## 3. Modal de Configuración (Filtros)
Al hacer click, se abre un *Modal Window*:

**Título:** Exportar Datos Operacionales
**Descripción:** Descargue un reporte CSV plano con el estado actual de los expedientes. (Límite: 6 meses de antigüedad).

**Filtros:**
- Rango de Fechas: `[DD/MM/YYYY] a [DD/MM/YYYY]`
- Nivel de Riesgo: `[ ] HIGH [ ] MEDIUM [ ] LOW [x] TODOS`
- Estado Expediente: `[ Dropdown (EVALUATION, BLOCKED, COMPLETED) ]`

**Botón Acción:**
`[ Generar y Descargar CSV ]`

## 4. Comportamiento (Background/Streaming)
- Al enviar la petición, la UI mostrará un *Toaster* (Notificación): `⏳ Preparando el archivo, la descarga iniciará pronto...`
- Si el usuario intentó solicitar más de 6 meses de datos, el modal arrojará un error de validación en rojo: `❌ Por favor limite la búsqueda a un máximo de 180 días. Para auditorías históricas, contacte a Sistemas.`
- El archivo descargado se llamará `supervisor_analytics_export.csv` y sus columnas vendrán "aplastadas" (Flattened) listas para ser procesadas en Excel.
