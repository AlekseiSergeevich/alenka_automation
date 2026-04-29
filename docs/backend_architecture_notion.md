# Backend Architecture For Order Automation

## 0. Executive Summary

- Рекомендуемая архитектура на старте: **modular monolith** на `FastAPI + PostgreSQL + background jobs`.
- БД для вашего кейса: **PostgreSQL**, а не MongoDB.
- ML-модуль на первом этапе не нужно выносить в отдельный сервис: лучше держать его как внутренний Python-модуль и запускать batch-расчет по расписанию или после обновления данных.
- Основная идея: **не считать прогноз "на лету" при каждом запросе UI**, а заранее сохранять рассчитанные рекомендации в БД.
- Ваш текущий код уже дает хорошую базу:
  - `src/data_loader/*` можно превратить в import pipeline.
  - `src/forecasting/random_forest_mvp.py` можно превратить в forecasting service.

---

## 1. Архитектура

### 1.1 Рекомендуемый подход

**Стартуйте не с микросервисов, а с одного backend-приложения**, внутри которого будут отдельные модули:

- `API layer`  
  Отдает данные фронту, принимает решения пользователя, запускает обновления.
- `Application layer`  
  Содержит бизнес-логику: сбор данных по городу, создание заказа, сохранение итогового решения.
- `Data access layer`  
  Работает с PostgreSQL через ORM/SQLAlchemy.
- `Import layer`  
  Загружает продажи и остатки из Excel/CSV, валидирует и сохраняет в БД.
- `ML/Forecast layer`  
  Строит прогноз и записывает результат в таблицы прогнозов.
- `Background jobs`  
  Запускают тяжелые операции вне HTTP-запроса: импорт, пересчет прогноза, регенерацию order draft.

### 1.2 Почему modular monolith лучше для вас

- Один репозиторий и один deploy проще поддерживать.
- Для junior/middle уровня такой проект легче дебажить.
- Не нужно сразу решать проблемы сетевого взаимодействия между сервисами.
- При этом код можно заранее разложить так, чтобы позже без боли выделить отдельный ML-сервис.

### 1.3 Компоненты системы

#### API

- `FastAPI`
- REST API для фронта
- Валидация входных данных через `Pydantic`
- Версионирование API через `/api/v1`

#### Основной backend

- Сервис агрегации данных по городу
- Сервис управления order batch
- Сервис сохранения решений пользователя
- Сервис получения последнего актуального прогноза

#### База данных

- `PostgreSQL`
- Хранит:
  - города
  - товары
  - продажи по месяцам
  - остатки
  - прогнозы
  - пользовательские решения
  - историю импорта
  - аудит изменений

#### ML-модуль

- Python-модуль внутри backend-проекта
- Использует уже существующую логику feature engineering
- На старте работает batch-режимом:
  - по расписанию
  - или после загрузки новых данных

#### Background jobs

- Для production удобно добавить:
  - `Celery + Redis` или `RQ + Redis`
- Для very-early MVP можно стартовать проще:
  - отдельная CLI-команда
  - cron
  - или manual trigger endpoint только для администратора

### 1.4 Схема взаимодействия компонентов

```text
Frontend
   |
   v
FastAPI API
   |
   +--> Application Services
   |       |
   |       +--> PostgreSQL
   |       |
   |       +--> Forecast Service
   |
   +--> Background Jobs
           |
           +--> Import raw sales/stocks
           +--> Validate data
           +--> Rebuild forecast
           +--> Save forecast results
```

### 1.5 Как будет выглядеть поток данных

#### Поток 1. Загрузка данных

1. Администратор загружает файл продаж или остатков.
2. Backend создает запись об импорте.
3. Файл парсится в staging-таблицы.
4. Выполняются проверки:
   - обязательные поля
   - корректность SKU
   - корректность города
   - дубликаты
   - консистентность названий
5. После валидации данные перекладываются в нормализованные таблицы.
6. После успешного импорта запускается пересчет прогнозов.

#### Поток 2. Получение таблицы для пользователя

1. Пользователь выбирает город.
2. API получает:
   - каталог товаров для города
   - продажи за последние 3 месяца
   - текущие остатки
   - последний прогноз
   - уже сохраненное пользовательское решение, если оно есть
3. Backend собирает единый DTO для UI.

#### Поток 3. Сохранение решения пользователя

1. Пользователь подтверждает или меняет рекомендованный заказ.
2. Backend сохраняет:
   - финальное количество
   - источник решения: `accepted` или `manual_override`
   - пользователя
   - timestamp
3. Изменение пишется в audit trail.

### 1.6 Как будет происходить расчет прогноза

#### Рекомендуемая стратегия

- **Прогноз считать batch-процессом**, а не внутри пользовательского запроса.
- Причина:
  - HTTP-запрос должен быть быстрым
  - ML-расчет тяжелее и может зависеть от объема данных
  - прогноз нужно воспроизводимо хранить с версией модели

#### Практический pipeline

1. Выбрать данные продаж по `city + sku` за достаточный горизонт.
2. Агрегировать продажи по месяцам.
3. Построить признаки:
   - лаги
   - rolling mean
   - rolling std
   - сезонные признаки месяца
   - unit-based признаки, если нужны
4. Рассчитать прогноз на следующий период.
5. Применить post-processing:
   - `prediction < 0 -> 0`
   - округление
   - минимальный порог заказа
   - бизнес-ограничения
6. Сохранить результат в `forecast_runs` и `forecast_results`.

#### Важно

- Модель должна возвращать **рекомендованный заказ**, а не просто "прогноз продаж", если бизнес-логика включает:
  - продажи
  - текущий остаток
  - safety stock
  - минимальную партию

#### Практическая формула для MVP

На первом этапе можно разделить задачу на 2 части:

1. `forecast_qty` = прогноз спроса на следующий период
2. `recommended_order_qty` = `max(forecast_qty + safety_stock - current_stock, 0)`

Это лучше, чем пытаться сразу обучить модель именно на "готовый заказ".

### 1.7 Как будет происходить работа с данными

#### Загрузка

- Источник:
  - Excel с продажами
  - Excel с остатками
- На старте загрузка может быть manual через admin endpoint.
- Позже можно добавить:
  - S3/MinIO
  - интеграцию с ERP/1C
  - scheduled sync

#### Хранение

- `raw_imports`
  - метаданные по файлу
  - статус обработки
  - ошибки
- `staging tables`
  - временные данные после парсинга
- `normalized tables`
  - production-таблицы для API и аналитики

#### Обновление

- Продажи:
  - upsert по ключу `city_id + sku + month`
- Остатки:
  - обычно snapshot на дату
  - не overwrite без истории
- Прогноз:
  - хранить новую версию расчета, а не перезаписывать старую без следа

### 1.8 Рекомендуемая модель данных

#### Основные таблицы

- `cities`
  - `id`
  - `name`

- `products`
  - `id`
  - `sku`
  - `name`
  - `unit`
  - `is_active`

- `city_products`
  - `city_id`
  - `product_id`
  - нужен, если ассортимент по городам различается

- `sales_monthly`
  - `id`
  - `city_id`
  - `product_id`
  - `month`
  - `qty`
  - `source_import_id`

- `stock_snapshots`
  - `id`
  - `city_id`
  - `product_id`
  - `snapshot_date`
  - `qty`
  - `source_import_id`

- `forecast_runs`
  - `id`
  - `city_id`
  - `model_name`
  - `model_version`
  - `trained_at`
  - `forecast_period`
  - `status`
  - `metrics_json`

- `forecast_results`
  - `id`
  - `forecast_run_id`
  - `city_id`
  - `product_id`
  - `forecast_qty`
  - `recommended_order_qty`
  - `confidence_score`

- `order_batches`
  - `id`
  - `city_id`
  - `forecast_run_id`
  - `status`
  - `created_by`
  - `created_at`

- `order_batch_items`
  - `id`
  - `order_batch_id`
  - `product_id`
  - `sales_last_3m`
  - `current_stock`
  - `recommended_order_qty`
  - `final_order_qty`
  - `decision_type`
  - `updated_by`
  - `updated_at`

- `decision_audit_log`
  - `id`
  - `order_batch_item_id`
  - `old_value`
  - `new_value`
  - `changed_by`
  - `changed_at`

- `imports`
  - `id`
  - `type`
  - `filename`
  - `status`
  - `started_at`
  - `finished_at`
  - `error_message`

### 1.9 PostgreSQL vs MongoDB

#### Сравнение под ваш кейс

| Критерий | PostgreSQL | MongoDB |
|---|---|---|
| Табличные данные: товары, города, остатки, прогнозы | Отлично подходит | Можно, но менее естественно |
| Джоины между сущностями | Сильная сторона | Сложнее и дороже в сопровождении |
| Транзакции | Надежно | Есть, но не главный сценарий Mongo |
| Агрегации и аналитика | Сильная сторона | Возможно, но хуже читается и поддерживается |
| Audit trail и история изменений | Удобно | Можно, но модель станет сложнее |
| Сложные выборки для UI | Удобно через SQL | Часто приводит к денормализации |
| Гибкая схема | Есть `JSONB` | Сильная сторона |
| Простота для этого домена | Лучше | Ниже |

#### Выбор

**Для этого проекта выбирайте PostgreSQL.**

#### Почему PostgreSQL лучше

- У вас доменная модель явно реляционная:
  - город
  - товар
  - продажи
  - остатки
  - прогнозы
  - решения пользователей
- Вам нужны:
  - надежные связи
  - уникальные ограничения
  - upsert
  - история изменений
  - агрегаты по периодам
- UI-таблица почти наверняка будет собираться через join нескольких источников.
- MongoDB особенно полезен, когда данные сильно документ-ориентированы и структура постоянно меняется. У вас не такой кейс.
- Если нужен semi-structured payload, в PostgreSQL можно хранить часть данных в `JSONB`.

#### Когда MongoDB имел бы смысл

- если бы у каждого товара был сильно разный и часто меняющийся набор атрибутов
- если бы основной поток данных был документный, а не аналитико-операционный
- если бы вы строили event/document систему без большого количества join

**Итог: PostgreSQL = лучший production choice для этого проекта.**

### 1.10 Рекомендуемый deployment stack

- `api` container
- `postgres` container
- `worker` container
- `redis` container, если используете очередь задач
- `nginx` или ingress на уровне инфраструктуры

---

## 2. API Design

### 2.1 Общие принципы

- Все endpoints под `/api/v1`
- Все write-операции идемпотентны там, где это возможно
- Для таблиц использовать pagination
- Для асинхронных импортов и пересчетов возвращать `job_id`

### 2.2 Получение данных по городу

#### Endpoint

- **Method:** `GET`
- **Path:** `/api/v1/cities/{city_id}/order-candidates`

#### Что делает

Возвращает таблицу для экрана формирования заказа:

- SKU
- название
- продажи за последние 3 месяца
- текущие остатки
- рекомендованный заказ
- финальное решение пользователя

#### Query params

- `batch_id` - optional, если хотим открыть конкретную сохраненную сессию
- `limit`
- `offset`
- `search`

#### Response example

```json
{
  "city": {
    "id": 3,
    "name": "Moscow"
  },
  "batch": {
    "id": 128,
    "status": "draft",
    "forecast_run_id": 55,
    "updated_at": "2026-04-10T11:20:00Z"
  },
  "items": [
    {
      "product_id": 101,
      "sku": "A-001",
      "name": "Конфеты трюфель",
      "unit": "шт",
      "sales_last_3m": 120,
      "current_stock": 40,
      "forecast_qty": 90,
      "recommended_order_qty": 60,
      "final_order_qty": 60,
      "decision_type": "accepted",
      "updated_at": "2026-04-10T11:15:00Z"
    }
  ],
  "meta": {
    "limit": 50,
    "offset": 0,
    "total": 321
  }
}
```

### 2.3 Получение прогноза

#### Endpoint

- **Method:** `GET`
- **Path:** `/api/v1/cities/{city_id}/forecasts/latest`

#### Что делает

Возвращает последний рассчитанный прогноз по городу.

#### Response example

```json
{
  "forecast_run": {
    "id": 55,
    "city_id": 3,
    "model_name": "random_forest",
    "model_version": "0.3.0",
    "forecast_period": "2026-04",
    "trained_at": "2026-04-10T07:00:00Z",
    "status": "completed",
    "metrics": {
      "mae": 12.4,
      "rmse": 18.1,
      "wape": 14.8
    }
  },
  "items": [
    {
      "sku": "A-001",
      "forecast_qty": 90,
      "recommended_order_qty": 60,
      "confidence_score": 0.82
    }
  ]
}
```

### 2.4 Запуск пересчета прогноза

#### Endpoint

- **Method:** `POST`
- **Path:** `/api/v1/cities/{city_id}/forecasts/recalculate`

#### Что делает

Запускает background-job на пересчет прогноза.

#### Request example

```json
{
  "forecast_period": "2026-04",
  "force_rebuild": false
}
```

#### Response example

```json
{
  "job_id": "job_8d7f21",
  "status": "queued"
}
```

### 2.5 Сохранение пользовательского решения

#### Endpoint

- **Method:** `PUT`
- **Path:** `/api/v1/order-batches/{batch_id}/items/{item_id}`

#### Что делает

Сохраняет изменение одной строки в заказе.

#### Request example

```json
{
  "final_order_qty": 75,
  "decision_type": "manual_override",
  "comment": "Увеличено из-за ожидаемой акции"
}
```

#### Response example

```json
{
  "item_id": 9001,
  "product_id": 101,
  "recommended_order_qty": 60,
  "final_order_qty": 75,
  "decision_type": "manual_override",
  "updated_by": 42,
  "updated_at": "2026-04-10T11:35:00Z"
}
```

### 2.6 Массовое сохранение решений

#### Endpoint

- **Method:** `PUT`
- **Path:** `/api/v1/order-batches/{batch_id}/items:bulk-save`

#### Request example

```json
{
  "items": [
    {
      "item_id": 9001,
      "final_order_qty": 75,
      "decision_type": "manual_override"
    },
    {
      "item_id": 9002,
      "final_order_qty": 30,
      "decision_type": "accepted"
    }
  ]
}
```

#### Response example

```json
{
  "batch_id": 128,
  "saved_items": 2,
  "status": "draft"
}
```

### 2.7 Обновление данных

#### Вариант A. Загрузка файла продаж

- **Method:** `POST`
- **Path:** `/api/v1/imports/sales`
- **Content-Type:** `multipart/form-data`

#### Response example

```json
{
  "import_id": 501,
  "status": "processing"
}
```

#### Вариант B. Загрузка файла остатков

- **Method:** `POST`
- **Path:** `/api/v1/imports/stocks`

#### Response example

```json
{
  "import_id": 502,
  "status": "processing"
}
```

#### Проверка статуса импорта

- **Method:** `GET`
- **Path:** `/api/v1/imports/{import_id}`

#### Response example

```json
{
  "id": 502,
  "type": "stocks",
  "status": "completed",
  "started_at": "2026-04-10T09:00:00Z",
  "finished_at": "2026-04-10T09:02:14Z",
  "errors": []
}
```

### 2.8 Рекомендуемые Pydantic-схемы

```python
class OrderCandidateItem(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: str
    sales_last_3m: Decimal
    current_stock: Decimal
    forecast_qty: Decimal
    recommended_order_qty: Decimal
    final_order_qty: Decimal | None
    decision_type: Literal["accepted", "manual_override", "pending"]


class UpdateOrderItemRequest(BaseModel):
    final_order_qty: Decimal = Field(ge=0)
    decision_type: Literal["accepted", "manual_override"]
    comment: str | None = Field(default=None, max_length=500)
```

---

## 3. Пошаговый план разработки

## Roadmap TODO

- [ ] Шаг 1. Спроектировать доменную модель и схему БД
- [ ] Шаг 2. Поднять каркас FastAPI-приложения
- [ ] Шаг 3. Подключить PostgreSQL и миграции
- [ ] Шаг 4. Реализовать import pipeline для продаж и остатков
- [ ] Шаг 5. Реализовать сбор таблицы для экрана заказа
- [ ] Шаг 6. Вынести ML-логику в backend-модуль
- [ ] Шаг 7. Добавить сохранение решений пользователя
- [ ] Шаг 8. Добавить background jobs и пересчет прогнозов
- [ ] Шаг 9. Покрыть ключевые сценарии тестами
- [ ] Шаг 10. Подготовить Docker и production baseline

<details>
<summary>Шаг 1. Спроектировать доменную модель и схему БД</summary>

- ✅ Что сделать
  - описать сущности `cities`, `products`, `sales_monthly`, `stock_snapshots`, `forecast_runs`, `forecast_results`, `order_batches`, `order_batch_items`
  - определить primary key, unique constraints и индексы
  - решить, какие данные хранятся как history, а какие как current snapshot
- 🎯 Результат
  - понятная схема БД, на которую можно опереть API и импорт
- 🛠 Инструменты
  - PostgreSQL
  - dbdiagram / draw.io / Mermaid
  - SQLAlchemy models
- 📚 Что изучить
  - `primary key`
  - `foreign key`
  - `unique constraint`
  - `index`
  - `normalization`
  - `upsert`

</details>

<details>
<summary>Шаг 2. Поднять каркас FastAPI-приложения</summary>

- ✅ Что сделать
  - создать базовую структуру проекта
  - подключить роутер `/api/v1`
  - настроить dependency injection для db session
  - добавить healthcheck endpoint
- 🎯 Результат
  - backend запускается локально и готов к развитию
- 🛠 Инструменты
  - FastAPI
  - Uvicorn
  - Pydantic
- 📚 Что изучить
  - `APIRouter`
  - `dependency injection`
  - `response model`
  - `request validation`

</details>

<details>
<summary>Шаг 3. Подключить PostgreSQL и миграции</summary>

- ✅ Что сделать
  - поднять PostgreSQL в Docker
  - подключить SQLAlchemy 2.0
  - добавить Alembic
  - создать первые миграции
- 🎯 Результат
  - база управляется через миграции, а не вручную
- 🛠 Инструменты
  - PostgreSQL
  - SQLAlchemy
  - Alembic
  - Docker Compose
- 📚 Что изучить
  - `SQLAlchemy session`
  - `ORM model`
  - `migration`
  - `transaction`

</details>

<details>
<summary>Шаг 4. Реализовать import pipeline для продаж и остатков</summary>

- ✅ Что сделать
  - переиспользовать логику из `src/data_loader/sales_loader.py`
  - переиспользовать логику из `src/data_loader/stock_loader.py`
  - добавить import status и error handling
  - сохранять валидные данные в нормализованные таблицы
- 🎯 Результат
  - данные загружаются в БД и готовы для API
- 🛠 Инструменты
  - pandas
  - openpyxl
  - background jobs
- 📚 Что изучить
  - `ETL`
  - `staging table`
  - `data validation`
  - `idempotency`

</details>

<details>
<summary>Шаг 5. Реализовать сбор таблицы для экрана заказа</summary>

- ✅ Что сделать
  - собрать SQL/query-service, который по `city_id` возвращает нужную таблицу
  - добавить продажи за последние 3 месяца
  - добавить последний актуальный остаток
  - добавить последний прогноз и сохраненное решение
- 🎯 Результат
  - фронт получает один готовый endpoint вместо нескольких
- 🛠 Инструменты
  - SQLAlchemy
  - PostgreSQL views или query service
- 📚 Что изучить
  - `join`
  - `aggregate`
  - `DTO`
  - `pagination`

</details>

<details>
<summary>Шаг 6. Вынести ML-логику в backend-модуль</summary>

- ✅ Что сделать
  - перенести логику из `src/forecasting/random_forest_mvp.py` в сервисный модуль
  - сделать вход: `city_id`, `forecast_period`
  - сделать выход: набор `forecast_results`
  - сохранять метрики и версию модели
- 🎯 Результат
  - прогноз считается не вручную в ноутбуке, а как часть backend-процесса
- 🛠 Инструменты
  - pandas
  - scikit-learn
  - job runner
- 📚 Что изучить
  - `feature engineering`
  - `offline inference`
  - `model versioning`
  - `batch scoring`

</details>

<details>
<summary>Шаг 7. Добавить сохранение решений пользователя</summary>

- ✅ Что сделать
  - endpoint для редактирования одной строки
  - endpoint для массового сохранения
  - audit log на каждое изменение
- 🎯 Результат
  - пользовательские правки надежно сохраняются и не теряются
- 🛠 Инструменты
  - FastAPI
  - PostgreSQL
  - Pydantic
- 📚 Что изучить
  - `optimistic locking`
  - `audit trail`
  - `bulk update`

</details>

<details>
<summary>Шаг 8. Добавить background jobs и пересчет прогнозов</summary>

- ✅ Что сделать
  - вынести тяжелые операции из HTTP-запросов
  - запускать импорт и forecast rebuild асинхронно
  - хранить статус jobs
- 🎯 Результат
  - API остается быстрым и стабильным
- 🛠 Инструменты
  - Celery или RQ
  - Redis
  - cron / scheduler
- 📚 Что изучить
  - `task queue`
  - `worker`
  - `retry`
  - `dead letter`

</details>

<details>
<summary>Шаг 9. Покрыть ключевые сценарии тестами</summary>

- ✅ Что сделать
  - unit tests на бизнес-логику
  - integration tests на API и БД
  - тесты на импорт файлов
  - smoke test на пересчет прогноза
- 🎯 Результат
  - изменения в backend не ломают базовые сценарии
- 🛠 Инструменты
  - pytest
  - httpx
  - testcontainers или отдельная test DB
- 📚 Что изучить
  - `unit test`
  - `integration test`
  - `fixture`
  - `test isolation`

</details>

<details>
<summary>Шаг 10. Подготовить Docker и production baseline</summary>

- ✅ Что сделать
  - собрать Dockerfile для API
  - добавить docker-compose для local dev
  - настроить env configs
  - настроить logging и health checks
- 🎯 Результат
  - проект можно стабильно запускать локально и выкатывать на сервер
- 🛠 Инструменты
  - Docker
  - Docker Compose
  - `.env`
- 📚 Что изучить
  - `12-factor app`
  - `containerization`
  - `health check`
  - `graceful shutdown`

</details>

---

## 4. Минимальный MVP

### 4.1 Что должно войти в первую рабочую версию

- загрузка продаж из Excel
- загрузка остатков из Excel
- хранение данных в PostgreSQL
- один endpoint для таблицы по городу
- batch-расчет прогноза
- сохранение ручных правок пользователя
- базовый Docker setup

### 4.2 Что можно отложить

- отдельный ML-сервис
- real-time пересчет
- сложные роли и права
- сложный мониторинг
- event bus
- multi-tenant архитектуру
- autoscaling
- прогнозы с ансамблями и MLOps-платформой

### 4.3 Как быстро получить первый результат

#### Самый короткий путь

1. Поднять `FastAPI + PostgreSQL + Docker Compose`
2. Сделать импорт текущих CSV/Excel в БД
3. Сделать endpoint `/cities/{id}/order-candidates`
4. Интегрировать текущий `random_forest_mvp.py` как offline batch script
5. Сохранять прогнозы в БД
6. Добавить endpoint сохранения решения

#### Реалистичный первый milestone

Через 1-2 недели можно получить backend, который:

- грузит данные
- считает прогноз
- отдает таблицу по городу
- сохраняет изменения пользователя

Этого уже достаточно для первого рабочего демо.

---

## 5. Best Practices

### 5.1 Как правильно структурировать FastAPI проект

```text
app/
  api/
    v1/
      endpoints/
        cities.py
        forecasts.py
        imports.py
        order_batches.py
      router.py
  core/
    config.py
    logging.py
    security.py
  db/
    base.py
    session.py
    models/
      city.py
      product.py
      sales.py
      stock.py
      forecast.py
      order_batch.py
      import_job.py
  schemas/
    city.py
    forecast.py
    import_job.py
    order_batch.py
  repositories/
    sales_repository.py
    stock_repository.py
    forecast_repository.py
    order_repository.py
  services/
    order_service.py
    forecast_service.py
    import_service.py
    city_dashboard_service.py
  ml/
    features.py
    train.py
    predict.py
    postprocess.py
  tasks/
    import_tasks.py
    forecast_tasks.py
  utils/
    time.py
  main.py

alembic/
tests/
docker/
```

### 5.2 Практические правила структуры

- роутеры не должны содержать тяжелую бизнес-логику
- бизнес-правила держите в `services/`
- прямой доступ к БД инкапсулируйте в `repositories/`
- схемы API и ORM-модели не смешивайте
- ML-код держите отдельно от HTTP-слоя

### 5.3 Как работать с конфигами

- Используйте `pydantic-settings`
- Все настройки через env vars:
  - `APP_ENV`
  - `DATABASE_URL`
  - `REDIS_URL`
  - `LOG_LEVEL`
  - `MODEL_PATH`
- Разделяйте:
  - `development`
  - `test`
  - `production`
- Никогда не хардкодьте секреты в коде

#### Пример

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "order-automation-api"
    app_env: str = "dev"
    database_url: str
    redis_url: str | None = None
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
```

### 5.4 Как логировать

- Логируйте в JSON или в строго структурированном формате
- На каждый запрос полезно писать:
  - `request_id`
  - `user_id`
  - `endpoint`
  - `duration_ms`
  - `status_code`
- На import/forecast jobs логируйте:
  - `job_id`
  - `city_id`
  - количество обработанных строк
  - количество ошибок
  - версию модели

#### Что важно не делать

- не логировать секреты
- не логировать весь payload без необходимости
- не смешивать business logs и debug noise

### 5.5 Как подготовить проект к масштабированию

- Держите API stateless
- Храните состояние в БД, а не в памяти процесса
- Тяжелые операции выносите в worker
- Сразу проектируйте таблицы с индексами по:
  - `city_id`
  - `product_id`
  - `month`
  - `forecast_run_id`
- Делайте API versioning
- Сохраняйте model version и import version
- Добавьте health checks:
  - liveness
  - readiness

### 5.6 Что еще критично для production

- Alembic миграции
- базовая авторизация
- rate limiting для admin/import endpoints
- retry policy для background jobs
- обработка частичных ошибок импорта
- observability:
  - logs
  - metrics
  - error tracking

---

## 6. Практическая рекомендация именно под ваш текущий проект

### Что я бы сделал на вашем месте прямо сейчас

1. Не переписывал бы текущие `data_loader` и `random_forest_mvp` с нуля.
2. Сначала обернул бы их в понятные сервисы backend-приложения.
3. Сразу перешел бы с CSV на PostgreSQL как на главный источник данных для API.
4. Ноутбуки оставил бы только для исследований и экспериментов.
5. В production-цепочке использовал бы только обычные Python-модули и фоновые задачи.

### Как переиспользовать уже написанное

- `src/data_loader/sales_loader.py`
  - использовать как основу для `import_service`
- `src/data_loader/stock_loader.py`
  - использовать как основу для загрузки snapshots остатков
- `src/data_loader/check_product_consistency.py`
  - встроить в validation stage
- `src/forecasting/random_forest_mvp.py`
  - разбить на:
    - `ml/features.py`
    - `ml/predict.py`
    - `services/forecast_service.py`

### Итоговое решение

**Если цель - быстро получить production-ready основу, то лучший путь такой:**

- `FastAPI`
- `PostgreSQL`
- `Docker Compose`
- `SQLAlchemy + Alembic`
- `Pydantic Settings`
- `background jobs for import/forecast`
- `ML как внутренний модуль, а не отдельный сервис`

Это даст вам:

- быстрый старт
- понятную кодовую базу
- нормальную масштабируемость
- минимальный архитектурный риск

