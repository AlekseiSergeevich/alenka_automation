import { useRef, useState, type ChangeEvent } from "react";
import { AlertTriangle, FileSpreadsheet, Upload } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { useOrderBlankStatusQuery, useOrderBlankUploadMutation } from "@/hooks/useOrderBlank";
import { isAuthUiDisabled } from "@/lib/authUi";
import { cn } from "@/lib/cn";

function formatAppliedAt(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function OrderBlankPage() {
  const { user } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pickedName, setPickedName] = useState<string | null>(null);

  const statusQuery = useOrderBlankStatusQuery();
  const uploadMutation = useOrderBlankUploadMutation();

  const isAdmin = isAuthUiDisabled() || user?.role === "admin";

  const onPick = () => {
    uploadMutation.reset();
    fileRef.current?.click();
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    uploadMutation.reset();
    const file = event.target.files?.[0];
    setPickedName(file?.name ?? null);
  };

  const onUpload = () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    uploadMutation.mutate(file, {
      onSettled: () => {
        resetFileInput(fileRef.current);
        setPickedName(null);
      },
    });
  };

  const st = statusQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Бланк заказа"
        description="Загрузка ежемесячного файла каталога (.xls / .xlsx): обновляет справочник товаров для прогноза и синхронизации."
      />

      {st?.needs_order_blank && st.warning ? (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> Требуется действие
          </AlertTitle>
          <AlertDescription>{st.warning}</AlertDescription>
        </Alert>
      ) : null}

      {statusQuery.isError ? (
        <Alert variant="warning">
          <AlertTitle>Не удалось загрузить статус</AlertTitle>
          <AlertDescription>{statusQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            Текущий статус
          </CardTitle>
          <CardDescription>
            Успешная загрузка в текущем календарном месяце снимает напоминание.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Товаров в каталоге: </span>
            <span className="font-medium tabular-nums">
              {statusQuery.isLoading ? "…" : (st?.product_count ?? "—")}
            </span>
          </p>
          <p>
            <span className="text-muted-foreground">Последняя успешная загрузка: </span>
            <span className="font-medium">{formatAppliedAt(st?.last_success_applied_at ?? null)}</span>
          </p>
          <p className="text-muted-foreground">
            Период напоминания: UTC‑месяц (как на сервере).
          </p>
        </CardContent>
      </Card>

      <Card className={cn(!isAdmin && "opacity-80")}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Загрузить файл
          </CardTitle>
          <CardDescription>
            Формат: .xls или .xlsx с листом «Бланк заказа», колонки УКП / КОД Продаж / Название SKU и др., как в
            вашей типовой выгрузке.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!isAdmin ? (
            <p className="text-sm text-muted-foreground">
              Загружать файл могут только администраторы. Обратитесь к админу или войдите под ролью
              admin.
            </p>
          ) : (
            <>
              <input
                ref={fileRef}
                type="file"
                accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                className="hidden"
                onChange={onFileChange}
              />
              <div className="flex flex-wrap items-center gap-3">
                <Button type="button" variant="outline" onClick={onPick}>
                  Выбрать файл
                </Button>
                <Button
                  type="button"
                  onClick={onUpload}
                  loading={uploadMutation.isPending}
                  disabled={!pickedName || uploadMutation.isPending}
                >
                  Отправить
                </Button>
                {pickedName ? (
                  <span className="text-sm text-muted-foreground truncate max-w-[240px]" title={pickedName}>
                    {pickedName}
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">Файл не выбран</span>
                )}
              </div>
              {uploadMutation.isError ? (
                <Alert variant="warning">
                  <AlertTitle>Ошибка загрузки</AlertTitle>
                  <AlertDescription>{uploadMutation.error.message}</AlertDescription>
                </Alert>
              ) : null}
              {uploadMutation.isSuccess ? (
                <Alert>
                  <AlertTitle>Готово</AlertTitle>
                  <AlertDescription>
                    Принято строк каталога: {uploadMutation.data.row_count}. Файл сохранён на сервере (
                    {uploadMutation.data.original_filename}
                    ).
                  </AlertDescription>
                </Alert>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function resetFileInput(input: HTMLInputElement | null) {
  if (input) {
    input.value = "";
  }
}
