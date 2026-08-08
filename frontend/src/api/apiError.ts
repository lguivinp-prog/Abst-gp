export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id?: string;
}

export class AppError extends Error {
  public status: number;
  public code: string;
  public isNetworkError: boolean;

  constructor(status: number, detail: ApiErrorDetail | string, isNetworkError: boolean = false) {
    const message = typeof detail === 'string' ? detail : detail.message;
    super(message);
    this.name = 'AppError';
    this.status = status;
    this.code = typeof detail === 'string' ? 'UNKNOWN' : detail.code;
    this.isNetworkError = isNetworkError;
  }
}

export const handleApiError = (error: any): never => {
  if (error.response) {
    // El servidor respondió con un status fuera del rango 2xx
    const status = error.response.status;
    const errorData = error.response.data?.error;
    
    if (errorData) {
      throw new AppError(status, errorData);
    }
    
    // Fallbacks genéricos
    switch (status) {
      case 401:
        throw new AppError(status, { code: 'UNAUTHORIZED', message: 'No autenticado o sesión expirada' });
      case 403:
        throw new AppError(status, { code: 'FORBIDDEN', message: 'No tiene permisos para esta acción' });
      case 404:
        throw new AppError(status, { code: 'NOT_FOUND', message: 'Recurso no encontrado' });
      case 422:
        throw new AppError(status, { code: 'VALIDATION_ERROR', message: 'Error de validación de datos' });
      case 500:
        throw new AppError(status, { code: 'INTERNAL_SERVER_ERROR', message: 'Error interno del servidor' });
      default:
        throw new AppError(status, { code: 'UNKNOWN_ERROR', message: `Error HTTP ${status}` });
    }
  } else if (error.request) {
    // La petición fue hecha pero no hubo respuesta
    throw new AppError(0, { code: 'NETWORK_ERROR', message: 'Error de red al contactar al servidor' }, true);
  } else {
    // Algo paso al configurar la petición
    throw new AppError(0, { code: 'CLIENT_ERROR', message: error.message }, false);
  }
};
