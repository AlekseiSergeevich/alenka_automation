# Candy Forecast — бэкенд

Бэкенд на FastAPI: агрегирует данные Saby Retail (точки, остатки, продажи) в
PostgreSQL и отдаёт пользователям денормализованное представление «магазин × товар».

## Быстрый старт

```bash
cd /Users/aleksejsuharev/Desktop/Аленка/candy_forecast
cp src/backend/.env.example src/backend/.env
.venv/bin/python -m pip install -r src/backend/requirements.txt

# Укажите DATABASE_URL в src/backend/.env, затем примените миграции:
.venv/bin/python -m alembic upgrade head

.venv/bin/python -m uvicorn src.backend.app.main:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>.

### Операционный ввод (скрипты в корне репозитория)

```bash
# Проверить DATABASE_URL (маскирован) и наличие настроек Saby:
.venv/bin/python scripts/check_env.py

# Если ещё нет src/backend/.env — скопировать из примера:
.venv/bin/python scripts/ensure_local_env.py

# После запуска API: полная синхронизация (points → все точки → stock + sales):
.venv/bin/python scripts/bootstrap_sync.py --base-url http://127.0.0.1:8000
```

Смоук-тесты API (нужна БД из `.env`): `pip install -r requirements-dev.txt && pytest`.

## Docker

Из корня репозитория (каталог с `Dockerfile` и `docker-compose.yml`):

```bash
cp src/backend/.env.example src/backend/.env
# Заполните учётные данные Saby в src/backend/.env (опционально env_file в compose).

docker compose up --build
```

- API: <http://127.0.0.1:8000/docs>
- PostgreSQL доступен на порту хоста `5432` (пользователь / пароль / БД: `postgres` /
  `postgres` / `candy_forecast`). Для продакшена смените порты или учётные данные в
  `docker-compose.yml`.

При каждом старте контейнера entrypoint выполняет `alembic upgrade head`, затем
запускает Uvicorn. `DATABASE_URL` внутри стека указывает на сервис `db`; переменные
из `src/backend/.env` подмешиваются, если файл есть (Compose `env_file` с `required: false`).

Чтобы запускать без локального `.env` (вызовы Saby не сработают, пока не передадите
учётные данные через `environment` или смонтированный файл), используйте версию Compose с
поддержкой опционального `env_file` или уберите блок `env_file` из
`docker-compose.yml` и передайте переменные вручную.

## Конфигурация

Сервис читает переменные окружения из `src/backend/.env` (см.
`src/backend/app/core/config.py`). Важные ключи:

- `DATABASE_URL` — DSN для async SQLAlchemy, например
  `postgresql+asyncpg://user:pass@localhost:5432/candy_forecast`.
- `TTL_POINTS_SECONDS`, `TTL_STOCK_SECONDS`, `TTL_SALES_SECONDS` — TTL, по которым
  оркестратор решает, свежие ли данные.
- `SALES_WINDOW_DAYS` — скользящее окно для агрегированного пользовательского представления (по умолчанию
  120 дней ≈ 4 месяца).
- `SALES_SYNC_OVERLAP_DAYS` — запас перекрытия для инкрементальной синхронизации продаж.
- `SABY_APP_CLIENT_ID`, `SABY_APP_SECRET`, `SABY_SECRET_KEY` — нужны для
  получения сервисного токена Saby. Для локальных экспериментов можно задать напрямую `SABY_ACCESS_TOKEN`.

## Архитектура

Слои соответствуют приложенному плану:

- **ingestion** (`app/ingestion/`): `sync_points`, `sync_stock`, `sync_sales`
  вызывают `SabyClient` и делают upsert нормализованных строк.
- **storage** (`app/db/`, `app/models/`, Alembic): PostgreSQL с таблицами `store`,
  `product`, `stock_current`, `sale_line`, `sync_run` и `agg_store_product`.
- **processing** (`app/services/`): `SyncOrchestrator` проверяет свежесть,
  берёт `pg_try_advisory_xact_lock`, запускает ingestion в транзакции,
  затем вызывает `refresh_aggregate` (один `INSERT ... ON CONFLICT`, пересобирающий
  строки в `agg_store_product` для затронутой области).
- **delivery** (`app/api/v1/endpoints/overview.py`): пользовательские чтения из
  `agg_store_product`.

## Пользовательский API (v1)

- `GET /api/v1/overview` — постраничный обзор по всем магазинам/товарам с
  фильтрами (`store_id`, `search`, `stock_gt`, `stock_lt`) и сортировкой
  (`days_of_cover`, `stock_balance`, `sales_qty_30d` и т.д.).
- `GET /api/v1/stores` — список известных торговых точек.
- `GET /api/v1/stores/{store_id}/products` — срез по одному магазину.
- `GET /api/v1/products/{article}` — один артикул по всем магазинам.

Каждое чтение также запускает фоновую проверку TTL через `BackgroundTasks`; устаревшие
ответы помечаются `meta.stale=true`.

## API администрирования / синхронизации

- `POST /api/v1/sync/{entity}?store_id=...&mode=auto|force` — запуск
  синхронизации (`points`, `stock`, `sales`). Для `stock` и `sales` обязателен `store_id`.
  `mode=force` выполняется синхронно вне зависимости от TTL; `mode=auto`
  планирует фоновое обновление, если данные устарели.
- `GET /api/v1/sync/status` — сводка по свежести для каждой отслеживаемой сущности.

## Отладочный API (прокси к Saby)

Эндпоинты под `/api/v1/saby/*` оставлены как тонкие прокси к API Saby для отладки и инспекции.
Они не обращаются к базе и не предназначены для конечных пользователей:

- `GET /api/v1/saby/status`
- `GET /api/v1/saby/sales-points`
- `GET /api/v1/saby/products`
- `GET /api/v1/saby/balances`
- `GET /api/v1/saby/sales`

## Структура каталогов

```text
src/backend/
  alembic/
    env.py
    script.py.mako
    versions/0001_initial.py
  app/
    api/
      deps.py
      v1/
        endpoints/
          health.py
          overview.py
          saby.py        # только отладочный прокси
          sync.py
        router.py
    core/
      config.py
    db/
      base.py
      session.py
    ingestion/
      points.py
      stock.py
      sales.py
      utils.py
    integrations/
      saby/
        client.py
        schemas.py       # фиксированный контракт с Saby, не менять
    models/
      aggregate.py
      product.py
      sale.py
      stock.py
      store.py
      sync.py
    services/
      aggregate.py
      orchestrator.py
    main.py
  .env.example
  .gitignore
  README.md
  requirements.txt
```

Alembic настроен в корне репозитория (`alembic.ini`); запускайте миграции оттуда.

## Ключи Saby

Локальные учётные данные Saby — в `src/backend/.env`.

Для сервисной авторизации Saby нужны:

```text
SABY_APP_CLIENT_ID=
SABY_APP_SECRET=
SABY_SECRET_KEY=
```

Документация по сервисной авторизации Saby:
<https://saby.ru/help/integration/api/auth/service>
