# Candy Forecast — бэкенд

Бэкенд на FastAPI: агрегирует данные Saby Retail (точки, остатки, продажи) в
PostgreSQL и отдаёт пользователям денормализованное представление «магазин × товар»
с помесячными продажами за последние N календарных месяцев.

Номенклатура для остатков берётся из прайс-листа точки: первый `id` из
`GET /retail/nomenclature/price-list` кэшируется в колонке `store.price_list_id` и
передаётся в `GET /retail/v2/nomenclature/list` как `priceListId` (см. миграцию `0006_plid`).

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

# После запуска API: полная синхронизация через один вызов
# (точки → для каждой точки склад и продажи помесячно):
.venv/bin/python scripts/bootstrap_sync.py --base-url http://127.0.0.1:8000

# Если включён AUTH_ENABLED: сначала логин, затем токен в CF_TOKEN или --token:
#   curl -X POST http://127.0.0.1:8000/api/v1/auth/login -H "Content-Type: application/json" \
#     -d '{"username":"admin","password":"..."}'  # взять access_token из ответа
#   export CF_TOKEN=...   # или .venv/bin/python scripts/bootstrap_sync.py --token "$CF_TOKEN"
```

Смоук-тесты API: `pip install -r requirements-dev.txt && pytest`. Если PostgreSQL недоступен,
часть смоуков (`/overview`, `/stores`, `/sync/status`) автоматически пропускается;
юнит-тесты месяцев и DTO запускаются без БД.

## Docker

Из корня репозитория (каталог с `Dockerfile` и `docker-compose.yml`):

```bash
cp src/backend/.env.example src/backend/.env
# Заполните учётные данные Saby в src/backend/.env (опционально env_file в compose).

docker compose up --build
```

**Production-оверлей** (без hot-reload и bind-mount кода, отключён debug API Saby по умолчанию в env):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

Переменные `APP_DEBUG`, `UVICORN_RELOAD`, `ENABLE_SABY_DEBUG_API` задайте в `src/backend/.env` или
в `environment` сервиса `api`, если переопределяете.

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
- `SALES_MONTHS_BACK` — сколько **календарных** месяцев тянуть из Saby и хранить
  помесячную статистику (по умолчанию `3`).
- `SALES_WINDOW_DAYS`, `SALES_SYNC_OVERLAP_DAYS` — оставлены для совместимости старых
  `.env`, текущая логика продаж построена на календарных месяцах.
- `SABY_APP_CLIENT_ID`, `SABY_APP_SECRET`, `SABY_SECRET_KEY` — нужны для
  получения сервисного токена Saby. Для локальных экспериментов можно задать напрямую `SABY_ACCESS_TOKEN`.
- **Авторизация** — `AUTH_ENABLED`, `SESSION_SECRET` (≥16 символов), пары
  `AUTH_ADMIN_*` / `AUTH_VIEWER_*` (bcrypt-хэш пароля, не пароль в открытом виде). См.
  `src/backend/.env.example`.
- **CORS для SPA** — `CORS_ALLOWED_ORIGINS` (список через запятую).
- **Документация API в проде** — `ENABLE_API_DOCS`, `ENABLE_OPENAPI_JSON` (можно выключить).
- **Прокси Saby** — `ENABLE_SABY_DEBUG_API` (`false` в production).

### Хэш пароля (bcrypt)

```bash
.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
```

### Контракт для frontend

См. [документацию контракта API](../../docs/API_CONTRACT.md) (типы, ошибки, `meta.stale`, decimal).

## Архитектура

Слои соответствуют приложенному плану:

- **ingestion** (`app/ingestion/`): `sync_points`, `sync_stock`, `sync_sales`
  вызывают `SabyClient`; продажи забираются **отдельным запросом на каждый календарный месяц**.
- **storage** (`app/db/`, `app/models/`, Alembic): PostgreSQL — `store`,
  `product`, `stock_current` (остатки на текущую дату), `sale_line` (строчный учёт продаж),
  `sales_monthly` (месячные агрегаты), `sync_run`, `agg_store_product` (вид для UI с JSON месяцев).
- **processing** (`app/services/`): `SyncOrchestrator` проверяет свежесть,
  берёт `pg_try_advisory_xact_lock`, запускает ingestion в транзакции,
  затем вызывает `refresh_aggregate`.
- **delivery** (`app/api/v1/endpoints/overview.py`): пользовательские чтения из
  `agg_store_product`.

## Пользовательский API (v1)

При `AUTH_ENABLED=true` все перечисленные ниже методы (кроме явно помеченных) требуют входа
(viewer или admin). Ошибки возвращаются в формате `{"error": {"code", "message", "request_id"}}`.

- `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me` — вход и текущий пользователь.

- `GET /api/v1/overview` — постраничный обзор по всем магазинам/товарам с
  фильтрами (`store_id`, `search`, `stock_gt`, `stock_lt`) и сортировкой
  (`days_of_cover`, `stock_balance`, `sales_qty_3m`, `avg_daily_qty` и т.д.).
  В каждой строке: `monthly_sales` (`month`, `qty`, `orders_count`) и сумма за период `sales_qty_3m`.
- `GET /api/v1/stores` — список известных торговых точек.
- `GET /api/v1/stores/{store_id}/products` — срез по одному магазину.
- `GET /api/v1/products/{article}` — один артикул по всем магазинам.

- `GET /api/v1/order-blank/status` — статус загрузки бланка заказа (последняя успешная
  загрузка, напоминание о месяце, число строк в каталоге `product`).
- `POST /api/v1/order-blank/upload` — только **admin**: multipart `file` (.xls), сохраняет
  файл в `ORDER_BLANK_STORAGE_DIR`, обновляет `product` как источник истины, пишет
  строку в `order_blank_upload`. После деплоя выполните `alembic upgrade head`, чтобы
  создать таблицу `order_blank_upload`.

В ответах `overview` / `stores/.../products` поле `meta.needs_order_blank` — «нужно
разгрести бланк»: пустой каталог **или** нет успешной загрузки в текущем UTC‑месяце.

Каждое чтение также запускает фоновую проверку TTL через `BackgroundTasks`; устаревшие
ответы помечаются `meta.stale=true`.

## API администрирования / синхронизации

Только роль **admin** (`POST` ниже). Просмотр статуса: `GET /api/v1/sync/status` — viewer и admin.

- `POST /api/v1/sync/bootstrap?mode=force` — **рекомендуемая первичная загрузка**:
  `points`, затем для каждого магазина `stock` и `sales`. Выполняется синхронно (долго на больших данных).
  Ручка должна быть объявлена **выше** `POST /sync/{entity}` во избежание конфликта маршрутов.
- `POST /api/v1/sync/{entity}?store_id=...&mode=auto|force` — точечная синхронизация
  (`points`, `stock`, `sales`). Для `stock` и `sales` нужен `store_id`.
  `mode=force` выполняется синхронно вне зависимости от TTL; `mode=auto`
  планирует фоновое обновление, если данные устарели.
- `GET /api/v1/sync/status` — сводка по свежести для `points` и для каждой точки
  `stock` / `sales`. Для `sales` добавляется поле `month_coverage` — покрыты ли месяцы
  в `sales_monthly` для каждого ожидаемого месяца.

## Отладочный API (прокси к Saby)

Эндпоинты под `/api/v1/saby/*` монтируются только если `ENABLE_SABY_DEBUG_API=true`.
Только роль **admin**. Это тонкие прокси к API Saby для отладки.
Они не пишут в базу данные напрямую:

- `GET /api/v1/saby/status`
- `GET /api/v1/saby/sales-points` (ответ приводится к DTO с точками продаж)
- `GET /api/v1/saby/products` / `catalog` (DTO номенклатуры / списков)
- `GET /api/v1/saby/balances`
- `GET /api/v1/saby/sales`
- `GET /api/v1/saby/price-list` (параметр `actualDate` по умолчанию — **сегодня** на момент запроса)

## Структура каталогов

```text
src/backend/
  alembic/
    env.py
    script.py.mako
    versions/0001_initial.py
    versions/0002_sales_monthly_and_agg_monthly_json.py
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
      month_ranges.py
      utils.py
    integrations/
      saby/
        client.py
        schemas.py       # pydantic-модели и разбор ключей ответов Saby
    models/
      aggregate.py
      product.py
      sale.py
      sales_monthly.py
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
