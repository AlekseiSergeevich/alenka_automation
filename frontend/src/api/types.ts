export interface UserDto {
  username: string;
  role: string;
}

export interface LoginRequestDto {
  username: string;
  password: string;
}

export interface LoginResponseDto {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserDto;
}

export interface StoreSummaryDto {
  id: number;
  name: string;
  address: string;
  locality: string;
}

export interface MonthlySalesBucketDto {
  month: string;
  qty: number;
  orders_count: number;
}

export interface AggRowDto {
  store_id: number;
  article: string;
  store_name: string;
  product_name: string;
  unit: string;
  stock_balance: number;
  stock_captured_at: string | null;
  monthly_sales: MonthlySalesBucketDto[];
  sales_qty_3m: number;
  avg_daily_qty: number;
  last_sale_at: string | null;
  days_of_cover: number | null;
  refreshed_at: string;
}

export interface OverviewMetaDto {
  total: number;
  limit: number;
  offset: number;
  stale: boolean;
  warning: string | null;
}

export interface OverviewResponseDto {
  meta: OverviewMetaDto;
  items: AggRowDto[];
}

export type SortField =
  | "store_id"
  | "article"
  | "product_name"
  | "stock_balance"
  | "sales_qty_3m"
  | "avg_daily_qty"
  | "days_of_cover"
  | "last_sale_at";

export type SortDirection = "asc" | "desc";

export interface ListStoreProductsParams {
  storeId: number;
  sort?: SortField;
  direction?: SortDirection;
  limit?: number;
  offset?: number;
}
