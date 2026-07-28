import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, FileSpreadsheet, MapPin, Search, Store } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { useOrderBlankStatusQuery } from "@/hooks/useOrderBlank";
import { useStoresQuery } from "@/hooks/useStores";
import type { StoreSummaryDto } from "@/api/types";
import { cn } from "@/lib/cn";

export function StoresPage() {
  const storesQuery = useStoresQuery();
  const orderBlankQuery = useOrderBlankStatusQuery();
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const data = storesQuery.data ?? [];
    const needle = search.trim().toLowerCase();
    if (!needle) return data;
    return data.filter((store) => {
      const haystack = `${store.name} ${store.locality} ${store.address}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [storesQuery.data, search]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Магазины"
        description="Выберите точку, чтобы посмотреть остатки и продажи по товарам."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Link
              to="/order-blank"
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm font-medium text-foreground transition-colors",
                "hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-muted-foreground",
              )}
            >
              <FileSpreadsheet className="h-4 w-4" />
              Бланк заказа
            </Link>
            {storesQuery.data ? (
              <Badge variant="secondary">{storesQuery.data.length} всего</Badge>
            ) : null}
          </div>
        }
      />

      {orderBlankQuery.data?.needs_order_blank && orderBlankQuery.data.warning ? (
        <Alert variant="warning">
          <AlertTitle>
            Бланк заказа{" "}
            <Link className="font-semibold underline-offset-4 hover:underline" to="/order-blank">
              — перейти к загрузке
            </Link>
          </AlertTitle>
          <AlertDescription>{orderBlankQuery.data.warning}</AlertDescription>
        </Alert>
      ) : null}

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Поиск по названию или городу"
          className="pl-9"
        />
      </div>

      {storesQuery.isLoading ? (
        <StoresSkeleton />
      ) : storesQuery.isError ? (
        <ErrorState
          title="Не удалось загрузить магазины"
          message={storesQuery.error.message}
          onRetry={() => storesQuery.refetch()}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Store className="h-5 w-5" />}
          title={search ? "Ничего не найдено" : "Нет магазинов"}
          description={
            search
              ? "Попробуйте изменить запрос или очистить фильтр."
              : "Когда появятся магазины, они отобразятся здесь."
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((store) => (
            <StoreCard key={store.id} store={store} />
          ))}
        </div>
      )}
    </div>
  );
}

function StoreCard({ store }: { store: StoreSummaryDto }) {
  return (
    <Link to={`/stores/${store.id}`} className="group block">
      <Card className="flex h-full flex-col gap-3 p-5 transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">

            <h3 className="text-base font-semibold leading-tight text-foreground">
              {store.name || "Без названия"}
            </h3>
          </div>
          <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </div>
        <div className="flex items-start gap-2 text-sm text-muted-foreground">
          <MapPin className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="space-y-0.5">
            <p className="text-foreground">{store.locality || "Город не указан"}</p>

          </div>
        </div>
      </Card>
    </Link>
  );
}

function StoresSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, idx) => (
        <Card key={idx} className="space-y-3 p-5">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-2/3" />
        </Card>
      ))}
    </div>
  );
}
