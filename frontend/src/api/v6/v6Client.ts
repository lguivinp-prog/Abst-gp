import type { AxiosRequestConfig } from 'axios';
import apiClient from '../client';

export const v6Client = {
  get: async <T>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<T> => {
    const response = await apiClient.get<T>(`/api/v6${url}`, config);
    return response.data;
  },

  post: async <T, D = unknown>(
    url: string,
    data?: D,
    config?: AxiosRequestConfig
  ): Promise<T> => {
    const response = await apiClient.post<T>(`/api/v6${url}`, data, config);
    return response.data;
  },

  put: async <T, D = unknown>(
    url: string,
    data?: D,
    config?: AxiosRequestConfig
  ): Promise<T> => {
    const response = await apiClient.put<T>(`/api/v6${url}`, data, config);
    return response.data;
  },

  delete: async <T>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<T> => {
    const response = await apiClient.delete<T>(`/api/v6${url}`, config);
    return response.data;
  },
};
