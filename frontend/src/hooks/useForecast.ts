import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { forecastApi } from "@/api/forecast";

export const forecastQueryKeys = {
  all: ["forecast"] as const,
  store: (storeId: number) => [...forecastQueryKeys.all, storeId] as const,
};

export function useForecastQuery(storeId: number, enabled = true) {
  return useQuery({
    queryKey: forecastQueryKeys.store(storeId),
    queryFn: () => forecastApi.getForecast(storeId),
    enabled,
    staleTime: 60_000,
  });
}

export function useGenerateForecastMutation() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (storeId: number) => forecastApi.generateForecast(storeId),
    onSuccess: (_, storeId) => {
      queryClient.invalidateQueries({ queryKey: forecastQueryKeys.store(storeId) });
    },
  });
}

export function useClearForecastMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (storeId: number) => forecastApi.clearForecast(storeId),
    onSuccess: (_, storeId) => {
      queryClient.invalidateQueries({ queryKey: forecastQueryKeys.store(storeId) });
    },
  });
}
