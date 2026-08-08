/**
 * Configuración global de límites de documentos y operaciones.
 * 
 * Los timeouts están en milisegundos (ms).
 * Los tamaños están en Megabytes (MB).
 */

// Timeout general para consultas asíncronas / endpoints ligeros
export const DEFAULT_API_TIMEOUT_MS = 15000; // 15 segundos

// Timeout masivo para operaciones síncronas bloqueantes pesadas (V4.9 backend limits)
export const QUOTATION_UPLOAD_TIMEOUT_MS = 120000; // 2 minutos (OCR Sincrónico)
export const COMPARISON_RUN_TIMEOUT_MS = 120000; // 2 minutos (Motor Comparador Sincrónico)

// Configuraciones de Polling (Worker)
export const DOCUMENT_POLLING_INTERVAL_MS = 2000; // 2 segundos
export const DOCUMENT_POLLING_TIMEOUT_MS = 300000; // 5 minutos de espera máxima

// Límites de tamaño de archivo UX (MB)
export const MAX_REQUIREMENT_SIZE_MB = Number((typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAX_REQ_SIZE_MB) || '25'); // 25MB default
export const MAX_QUOTATION_SIZE_MB = Number((typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAX_QUOT_SIZE_MB) || '25'); // 25MB default

