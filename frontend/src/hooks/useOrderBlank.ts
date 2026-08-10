import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { orderBlankApi } from "@/api/orderBlank";
import { storesQueryKeys } from "@/hooks/useStores";

export const orderBlankQueryKeys = {
  all: ["order-blank"] as const,
  status: () => [...orderBlankQueryKeys.all, "status"] as const,
};

export function useOrderBlankStatusQuery() {
  return useQuery({
    queryKey: orderBlankQueryKeys.status(),
    queryFn: () => orderBlankApi.status(),
    staleTime: 30_000,
  });
}

export function useOrderBlankUploadMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => orderBlankApi.upload(file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: orderBlankQueryKeys.status() });
      await queryClient.invalidateQueries({ queryKey: storesQueryKeys.all });
    },
  });
}
