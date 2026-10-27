/**
 * API Client — Interceptor de autenticacion y manejo de 401.
 *
 * P14-R2-15: Token de acceso leido EXCLUSIVAMENTE de sessionStorage.
 * localStorage fue eliminado como fuente de tokens.
 */

import axios from 'axios';

const apiClient = axios.create({
  baseURL: (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || '',
  headers: {
    'Content-type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  // Excluir /auth/token del interceptor para evitar enviar tokens expirados en el login
  if (config.url && config.url.includes('/auth/token')) {
    return config;
  }
  // P14-R2-15: Solo sessionStorage — localStorage eliminado
  const token = (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('access_token') : null);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  if (config.data instanceof FormData) {
    delete config.headers['Content-type'];
    delete config.headers['Content-Type'];
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      const isAuthTokenEndpoint = error.config?.url?.includes('/auth/token');
      // Solo forzamos logout si el 401 NO viene del intento de login en sí
      if (!isAuthTokenEndpoint && typeof window !== 'undefined') {
        sessionStorage.removeItem('access_token');
        // P14-R2-15: localStorage eliminado — no se limpia lo que no existe
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
