import { useMemo, useState } from "react";
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
} from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import type { AggRowDto } from "@/api/types";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

const HIGHLIGHT_MULTIPLIER = 1.2;

interface ProductRow {
  raw: AggRowDto;
  productName: string;
  article: string;
  stock: number;
  lastMonthQty: number | null;
  twoMonthsAgoQty: number | null;
  threeMonthsAgoQty: number | null;
  isAtRisk: boolean;
}

function buildRows(items: AggRowDto[]): ProductRow[] {
  return items.map((row) => {
    const sorted = [...row.monthly_sales].sort((a, b) =>
      a.month < b.month ? 1 : a.month > b.month ? -1 : 0,
    );
    const lastMonth = sorted[0]?.qty ?? null;
    const twoBack = sorted[1]?.qty ?? null;
    const threeBack = sorted[2]?.qty ?? null;
    const stock = Number(row.stock_balance) || 0;
    const lastMonthValue = lastMonth ?? 0;
    const isAtRisk = lastMonthValue * HIGHLIGHT_MULTIPLIER >= stock;

    return {
      raw: row,
      productName: row.product_name || row.article,
      article: row.article,
      stock,
      lastMonthQty: lastMonth,
      twoMonthsAgoQty: twoBack,
      threeMonthsAgoQty: threeBack,
      isAtRisk,
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
      limit: 1000,
    },
    validStoreId,
  );

  const store = storesQuery.data?.find((item) => item.id === storeId) ?? null;
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "productName", desc: false },
  ]);

  const rows = useMemo(
    () => buildRows(productsQuery.data?.items ?? []),
    [productsQuery.data?.items],
  );

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
        cell: () => <span className="text-muted-foreground">—</span>,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, globalFilter: search },
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
          </div>
        }
      />

      {meta?.stale && meta.warning ? (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> Данные обновляются
          </AlertTitle>
          <AlertDescription>{meta.warning}</AlertDescription>
        </Alert>
      ) : null}

      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по названию или артикулу"
              className="pl-9"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Подсветка: остаток ниже порога продаж × {HIGHLIGHT_MULTIPLIER.toString()}
          </p>
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
          <Table>
            <TableHeader>
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
