import { useQuery } from "@tanstack/react-query";
import { storesApi } from "@/api/stores";
import type { ListStoreProductsParams } from "@/api/types";

export const storesQueryKeys = {
  all: ["stores"] as const,
  list: () => [...storesQueryKeys.all, "list"] as const,
  products: (params: ListStoreProductsParams) =>
    [...storesQueryKeys.all, "products", params] as const,
};

export function useStoresQuery() {
  return useQuery({
    queryKey: storesQueryKeys.list(),
    queryFn: () => storesApi.list(),
    staleTime: 60_000,
  });
}

export function useStoreProductsQuery(params: ListStoreProductsParams, enabled = true) {
  return useQuery({
    queryKey: storesQueryKeys.products(params),
    queryFn: () => storesApi.listProducts(params),
    enabled,
    staleTime: 30_000,
  });
}
