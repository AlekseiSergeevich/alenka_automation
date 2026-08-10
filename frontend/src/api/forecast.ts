import { apiRequest } from "./client";
import type { ForecastResponseDto } from "./types";

export const forecastApi = {
  getForecast: async (storeId: number): Promise<ForecastResponseDto> => {
    return apiRequest<ForecastResponseDto>(`api/v1/forecast/${storeId}`);
  },
  generateForecast: async (storeId: number): Promise<ForecastResponseDto> => {
    return apiRequest<ForecastResponseDto>(`api/v1/forecast/${storeId}/generate`, { method: "POST" });
  },
  clearForecast: async (storeId: number): Promise<void> => {
    return apiRequest<void>(`api/v1/forecast/${storeId}`, { method: "DELETE" });
  }
};
