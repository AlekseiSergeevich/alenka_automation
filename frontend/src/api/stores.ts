import { apiRequest } from "@/api/client";
import type {
  ListStoreProductsParams,
  OverviewResponseDto,
  StoreSummaryDto,
} from "@/api/types";

export const storesApi = {
  list: () => apiRequest<StoreSummaryDto[]>("/api/v1/stores"),
  listProducts: ({
    storeId,
    sort = "product_name",
    direction = "asc",
    limit = 5000,
    offset = 0,
  }: ListStoreProductsParams) =>
    apiRequest<OverviewResponseDto>(`/api/v1/stores/${storeId}/products`, {
      query: { sort, direction, limit, offset },
    }),
};
