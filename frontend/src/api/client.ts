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
  if (typeof localStorage !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
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
      if (!isAuthTokenEndpoint && typeof localStorage !== 'undefined' && typeof window !== 'undefined') {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
