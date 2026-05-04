# Контракт API для frontend (Candy Forecast)

Сводка для клиента (SPA, OpenAPI code generation). Актуальные схемы: `/openapi.json`
(если `ENABLE_OPENAPI_JSON=true`).

## Аутентификация

- Если `AUTH_ENABLED=false` (локально): все защищённые эндпоинты доступны без входа.
- Если `AUTH_ENABLED=true`:
  - `POST /api/v1/auth/login` — тело `{ "username", "password" }`; ответ содержит `access_token`
    и выставляет HttpOnly cookie сессии (имя из `SESSION_COOKIE_NAME`).
  - Дальше передавать либо cookie (same-origin / настроенный CORS с credentials), либо заголовок
    `Authorization: Bearer <access_token>`.
  - Роли: `viewer` — чтение overview/stores/products и `GET /sync/status`; `admin` — также
    `POST /sync/*` и прокси `/api/v1/saby/*` (если включён).

## Формат ошибок

Ответы об ошибках имеют вид:

```json
{
  "error": {
    "code": "HTTP_401",
    "message": "Not authenticated",
    "request_id": "uuid-or-null"
  }
}
```

422 validation: `code: "validation_error"`, `message` — массив ошибок Pydantic (как в FastAPI).

## Денежные/количественные поля

Поля `Decimal` в JSON сериализуются **как строки** (например `"12.5"`), чтобы не терять точность.
Парсить в `Decimal` / `Big` на клиенте.

## Чтения

- `GET /api/v1/overview` — пагинация `limit` / `offset`, сортировка `sort` + `direction`, фильтры
  `store_id`, `search`, `stock_gt`, `stock_lt`.
- `meta.stale` — `true`, если фоновая синхронизация ещё обновляет данные; `meta.warning` — текст
  для UI (при необходимости показать «обновляется…»).
- `GET /api/v1/stores` — список точек.
- `GET /api/v1/stores/{store_id}/products` — срез по магазину.
- `GET /api/v1/products/{article}` — артикул по всем магазинам.

## Синхронизация (admin)

- `POST /api/v1/sync/bootstrap?mode=force` — долгая полная загрузка.
- `POST /api/v1/sync/{entity}` — `points` | `stock` | `sales` (для stock/sales нужен `store_id`).

## Проверки здоровья (без auth)

- `GET /health` — liveness.
- `GET /health/ready` — readiness; 503 если БД недоступна.

## CORS

Список origin задаётся `CORS_ALLOWED_ORIGINS` (через запятую). Для cookie-сессий с другого origin
нужны корректные `SameSite` / `Secure` (см. `SESSION_COOKIE_*` в `.env.example`).
