import { useMemo, useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  PackageSearch,
  Search,
  Check,
  CheckCircle2,
  BrainCircuit,
  FileDown,
  X,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { useStoreProductsQuery, useStoresQuery } from "@/hooks/useStores";
import { useForecastQuery, useGenerateForecastMutation, useClearForecastMutation } from "@/hooks/useForecast";
import type { AggRowDto } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

const HIGHLIGHT_MULTIPLIER = 1.2;

interface ProductRow {
  raw: AggRowDto;
  productName: string;
  article: string;
  rating: string;
  stock: number;
  lastMonthQty: number | null;
  twoMonthsAgoQty: number | null;
  threeMonthsAgoQty: number | null;
  isAtRisk: boolean;
  recommendedQty: number | null;
}

function buildRows(items: AggRowDto[], forecastMap: Record<string, number>): ProductRow[] {
  const currentMonthStart = new Date().toISOString().substring(0, 7) + "-01";
  
  return items.map((row) => {
    const historicalSales = row.monthly_sales.filter((s) => s.month < currentMonthStart);
    const sorted = [...historicalSales].sort((a, b) =>
      a.month < b.month ? 1 : a.month > b.month ? -1 : 0,
    );
    const lastMonth = sorted[0]?.qty ?? null;
    const twoBack = sorted[1]?.qty ?? null;
    const threeBack = sorted[2]?.qty ?? null;
    const stock = Number(row.stock_balance) || 0;
    const recommendedQty = forecastMap[row.article] ?? null;
    const isAtRisk = recommendedQty !== null && recommendedQty > 0;

    return {
      raw: row,
      productName: row.product_name || row.article,
      article: row.article,
      rating: row.rating || "",
      stock,
      lastMonthQty: lastMonth,
      twoMonthsAgoQty: twoBack,
      threeMonthsAgoQty: threeBack,
      isAtRisk,
      recommendedQty,
    };
  });
}

export function StorePage() {
  const params = useParams<{ storeId: string }>();
  const storeId = Number(params.storeId);
  const validStoreId = Number.isFinite(storeId) && storeId > 0;

  const storesQuery = useStoresQuery();
  const productsQuery = useStoreProductsQuery(
    {
      storeId,
      sort: "product_name",
      direction: "asc",
      limit: 5000,
    },
    validStoreId,
  );

  const forecastQuery = useForecastQuery(storeId, validStoreId);
  const generateForecastMutation = useGenerateForecastMutation();
  const clearForecastMutation = useClearForecastMutation();

  const store = storesQuery.data?.find((item) => item.id === storeId) ?? null;
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "productName", desc: false },
  ]);
  const [orderValues, setOrderValues] = useState<Record<string, string>>({});
  const [approvedSkus, setApprovedSkus] = useState<Set<string>>(new Set());

  const forecastMap = useMemo(() => {
    const map: Record<string, number> = {};
    if (forecastQuery.data?.forecast) {
      for (const item of forecastQuery.data.forecast) {
        map[item.sku] = item.recommended_qty;
      }
    }
    return map;
  }, [forecastQuery.data]);

  const rows = useMemo(
    () => buildRows(productsQuery.data?.items ?? [], forecastMap),
    [productsQuery.data?.items, forecastMap],
  );

  const [filterMode, setFilterMode] = useState<"all" | "recommended" | "not_recommended">("all");
  const [showOnlyWithHistory, setShowOnlyWithHistory] = useState(false);

  const filteredRows = useMemo(() => {
    let result = rows;
    if (showOnlyWithHistory) {
      result = result.filter(r => r.raw.monthly_sales && r.raw.monthly_sales.length > 0);
    }
    
    if (filterMode === "recommended") {
      return result.filter(r => (r.recommendedQty !== null && r.recommendedQty > 0) || (orderValues[r.article] && orderValues[r.article] !== "0"));
    }
    if (filterMode === "not_recommended") {
      return result.filter(r => (r.recommendedQty === null || r.recommendedQty <= 0) && (!orderValues[r.article] || orderValues[r.article] === "0"));
    }
    return result;
  }, [rows, filterMode, orderValues, showOnlyWithHistory]);

  useEffect(() => {
    if (forecastQuery.data?.forecast) {
      setOrderValues((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const item of forecastQuery.data.forecast) {
          if (next[item.sku] === undefined && item.recommended_qty > 0) {
            next[item.sku] = Math.ceil(item.recommended_qty).toString();
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }
  }, [forecastQuery.data]);

  const columns = useMemo<ColumnDef<ProductRow>[]>(
    () => [
      {
        id: "productName",
        accessorKey: "productName",
        header: "Товар",
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <p className="font-medium text-foreground">{row.original.productName}</p>
            <p className="text-xs text-muted-foreground">
              арт. {row.original.article}
              {row.original.raw.unit ? ` · ${row.original.raw.unit}` : ""}
            </p>
          </div>
        ),
        filterFn: (row, _columnId, filterValue) => {
          const needle = String(filterValue ?? "").trim().toLowerCase();
          if (!needle) return true;
          const haystack = `${row.original.productName} ${row.original.article}`.toLowerCase();
          return haystack.includes(needle);
        },
      },

      {
        id: "stock",
        accessorKey: "stock",
        header: "Остаток",
        cell: ({ row }) => (
          <NumberCell value={row.original.stock} highlighted={row.original.isAtRisk} />
        ),
        sortingFn: "basic",
      },
      {
        id: "lastMonth",
        accessorKey: "lastMonthQty",
        header: "Последний месяц",
        cell: ({ row }) => <NumberCell value={row.original.lastMonthQty} />,
      },
      {
        id: "twoMonthsAgo",
        accessorKey: "twoMonthsAgoQty",
        header: "2 мес. назад",
        cell: ({ row }) => <NumberCell value={row.original.twoMonthsAgoQty} />,
      },
      {
        id: "threeMonthsAgo",
        accessorKey: "threeMonthsAgoQty",
        header: "3 мес. назад",
        cell: ({ row }) => <NumberCell value={row.original.threeMonthsAgoQty} />,
      },
      {
        id: "recommended",
        header: "Рекомендация",
        enableSorting: false,
        cell: ({ row, table }) => {
          const meta = table.options.meta as any;
          const { orderValues, setOrderValues, approvedSkus, setApprovedSkus } = meta;
          const sku = row.original.article;
          const isApproved = approvedSkus.has(sku);
          const val = orderValues[sku] ?? "";
          const rec = row.original.recommendedQty;
          
          return (
            <div className="flex items-center gap-2">
              <div className="relative">
                <Input 
                  type="text"
                  inputMode="numeric"
                  value={val}
                  onChange={(e) => {
                    const onlyDigits = e.target.value.replace(/\D/g, "");
                    setOrderValues((prev: any) => ({ ...prev, [sku]: onlyDigits }));
                    if (isApproved) {
                      const newSet = new Set(approvedSkus);
                      newSet.delete(sku);
                      setApprovedSkus(newSet);
                    }
                  }}
                  placeholder={rec !== null ? Math.ceil(rec).toString() : "-"}
                  className={cn("w-20 text-right h-8 font-medium", isApproved && "border-green-500 bg-green-50 text-green-900")}
                />
              </div>
              <Button 
                size="icon" 
                variant="ghost" 
                className={cn("h-8 w-8", isApproved ? "text-green-600 hover:text-green-700 hover:bg-green-100" : "text-muted-foreground hover:text-foreground")}
                onClick={() => {
                  const newSet = new Set(approvedSkus);
                  if (isApproved) newSet.delete(sku); else newSet.add(sku);
                  setApprovedSkus(newSet);
                }}
              >
                <CheckCircle2 className="h-5 w-5" />
              </Button>
            </div>
          );
        },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting, globalFilter: search },
    meta: { orderValues, setOrderValues, approvedSkus, setApprovedSkus },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: (row, _columnId, filterValue) => {
      const needle = String(filterValue ?? "").trim().toLowerCase();
      if (!needle) return true;
      const haystack = `${row.original.productName} ${row.original.article}`.toLowerCase();
      return haystack.includes(needle);
    },
  });

  const meta = productsQuery.data?.meta;
  const atRiskCount = rows.filter((row) => row.isAtRisk).length;

  const handleBulkApprove = () => {
    if (approvedSkus.size > 0) {
      setApprovedSkus(new Set());
    } else {
      const newSet = new Set(approvedSkus);
      rows.forEach(r => {
        if (r.recommendedQty !== null || orderValues[r.article]) {
          newSet.add(r.article);
        }
      });
      setApprovedSkus(newSet);
    }
  };

  const handleGenerateOrder = async () => {
    if (approvedSkus.size === 0) return;
    
    const orders: Record<string, number> = {};
    for (const sku of approvedSkus) {
      const val = orderValues[sku];
      if (val) {
        orders[sku] = parseInt(val, 10);
      } else {
        const row = rows.find(r => r.article === sku);
        if (row && row.recommendedQty !== null) {
          orders[sku] = Math.ceil(row.recommendedQty);
        }
      }
    }

    try {
      const response = await fetch('/api/v1/order-blank/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ store_id: storeId, orders })
      });
      
      if (!response.ok) throw new Error('Не удалось сформировать заказ');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `order_store_${storeId}.xls`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error(err);
      alert('Ошибка при формировании заказа');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/stores"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          Все магазины
        </Link>
      </div>

      <PageHeader
        title={store?.name ?? (validStoreId ? `Магазин #${storeId}` : "Магазин")}
        description={
          store
            ? [store.locality, store.address].filter(Boolean).join(" · ")
            : undefined
        }
        actions={
          <div className="flex items-center gap-2">
            {meta ? (
              <Badge variant="secondary">{meta.total} товаров</Badge>
            ) : null}
            {atRiskCount > 0 ? (
              <Badge variant="danger">{atRiskCount} требуют внимания</Badge>
            ) : null}
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => generateForecastMutation.mutate(storeId)}
              disabled={generateForecastMutation.isPending}
            >
              <BrainCircuit className="mr-2 h-4 w-4 text-purple-500" />
              {generateForecastMutation.isPending ? "Генерация..." : "Сформировать рекомендацию"}
            </Button>
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => {
                if (window.confirm("Вы точно хотите удалить рекомендацию?")) {
                  clearForecastMutation.mutate(storeId);
                }
              }}
              disabled={clearForecastMutation.isPending || (!forecastQuery.data?.forecast?.length && !forecastQuery.isPending)}
            >
              <Trash2 className="mr-2 h-4 w-4 text-red-500" />
              Очистить
            </Button>
            <Button 
              variant={approvedSkus.size > 0 ? "destructive" : "primary"}
              size="sm"
              onClick={handleBulkApprove}
            >
              {approvedSkus.size > 0 ? (
                <>
                  <X className="mr-2 h-4 w-4" />
                  Отменить все
                </>
              ) : (
                <>
                  <Check className="mr-2 h-4 w-4" />
                  Принять все
                </>
              )}
            </Button>
            <Button 
              variant="primary" 
              size="sm"
              className="bg-green-600 hover:bg-green-700 text-white"
              onClick={handleGenerateOrder}
              disabled={approvedSkus.size === 0}
            >
              <FileDown className="mr-2 h-4 w-4" />
              Сформировать заказ
            </Button>
          </div>
        }
      />

      {meta?.warning ? (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {meta.stale ? "Данные обновляются" : "Внимание"}
          </AlertTitle>
          <AlertDescription>{meta.warning}</AlertDescription>
        </Alert>
      ) : meta?.total !== undefined && meta.total > 0 ? (
        <Alert className="border-green-200 bg-green-50 text-green-900">
          <AlertTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            Данные загружены
          </AlertTitle>
          <AlertDescription>
            Остатки актуальны. Все товары успешно загружены из СБИС.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col sm:flex-row gap-3 w-full">
            <div className="relative w-full max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Поиск по названию или артикулу"
                className="pl-9"
              />
            </div>
            <div className="flex items-center gap-1 bg-muted/50 p-1 rounded-lg border border-border shrink-0">
              <Button
                variant={filterMode === "all" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setFilterMode("all")}
                className={cn("h-8 text-xs", filterMode === "all" ? "bg-background shadow-sm" : "")}
              >
                Все
              </Button>
              <Button
                variant={filterMode === "recommended" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setFilterMode("recommended")}
                className={cn("h-8 text-xs", filterMode === "recommended" ? "bg-background shadow-sm" : "")}
              >
                Требуют пополнения
              </Button>
              <Button
                variant={filterMode === "not_recommended" ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setFilterMode("not_recommended")}
                className={cn("h-8 text-xs", filterMode === "not_recommended" ? "bg-background shadow-sm" : "")}
              >
                Достаточный остаток
              </Button>
            </div>
            <div className="flex items-center gap-1 bg-muted/50 p-1 rounded-lg border border-border shrink-0">
              <Button
                variant={showOnlyWithHistory ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setShowOnlyWithHistory(v => !v)}
                className={cn("h-8 text-xs", showOnlyWithHistory ? "bg-background shadow-sm text-blue-600" : "")}
              >
                Только с продажами
              </Button>
            </div>
          </div>
        </div>

        {!validStoreId ? (
          <div className="p-6">
            <ErrorState
              title="Неверный идентификатор магазина"
              message="Откройте список магазинов и выберите нужный."
            />
          </div>
        ) : productsQuery.isLoading ? (
          <ProductsSkeleton />
        ) : productsQuery.isError ? (
          <div className="p-6">
            <ErrorState
              title="Не удалось загрузить товары"
              message={productsQuery.error.message}
              onRetry={() => productsQuery.refetch()}
            />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<PackageSearch className="h-5 w-5" />}
              title="В этом магазине пока нет товаров"
              description="Когда данные подтянутся из источника, они появятся здесь."
            />
          </div>
        ) : table.getRowModel().rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Search className="h-5 w-5" />}
              title="Ничего не найдено"
              description="Попробуйте изменить запрос."
            />
          </div>
        ) : (
          <Table wrapperClassName="max-h-[calc(100vh-250px)]">
            <TableHeader className="sticky top-0 bg-background/95 backdrop-blur z-10 shadow-sm">
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id} className="hover:bg-transparent">
                  {headerGroup.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const sortDir = header.column.getIsSorted();
                    return (
                      <TableHead key={header.id}>
                        {header.isPlaceholder ? null : (
                          <button
                            type="button"
                            className={cn(
                              "inline-flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-muted-foreground",
                              canSort && "hover:text-foreground",
                              !canSort && "cursor-default",
                            )}
                            onClick={
                              canSort
                                ? header.column.getToggleSortingHandler()
                                : undefined
                            }
                          >
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                            {canSort ? (
                              sortDir === "asc" ? (
                                <ArrowUp className="h-3.5 w-3.5" />
                              ) : sortDir === "desc" ? (
                                <ArrowDown className="h-3.5 w-3.5" />
                              ) : (
                                <ArrowUpDown className="h-3.5 w-3.5 opacity-60" />
                              )
                            ) : null}
                          </button>
                        )}
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={cn(
                    row.original.isAtRisk && "bg-red-50 hover:bg-red-100/70",
                    approvedSkus.has(row.original.article) && "bg-green-50/50 hover:bg-green-100/50"
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function NumberCell({
  value,
  highlighted,
}: {
  value: number | null | undefined;
  highlighted?: boolean;
}) {
  return (
    <span
      className={cn(
        "tabular-nums",
        highlighted && "font-semibold text-red-700",
      )}
    >
      {formatNumber(value)}
    </span>
  );
}

function ProductsSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 8 }).map((_, idx) => (
        <div key={idx} className="grid grid-cols-6 gap-4 px-4 py-3">
          <Skeleton className="col-span-2 h-5" />
          <Skeleton className="h-5" />
          <Skeleton className="h-5" />
          <Skeleton className="h-5" />
          <Skeleton className="h-5" />
        </div>
      ))}
    </div>
  );
}
