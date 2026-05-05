# Candy Forecast — Frontend

React + TypeScript + Vite интерфейс для backend `src/backend`.

## Стек

- **React 18** + **TypeScript** + **Vite 5**
- **TailwindCSS** + лёгкий shadcn-подобный UI kit
- **TanStack Query** для запросов
- **TanStack Table** для таблиц
- **React Router** для маршрутизации

## Быстрый старт

```bash
cd frontend
npm install
npm run dev
```

По умолчанию dev-сервер слушает `http://localhost:5173` и проксирует запросы `/api` и `/health` на `http://127.0.0.1:8000` (см. `vite.config.ts`). Для запуска backend используйте инструкцию из `src/backend/README.md`.

## Docker (весь стек из корня репозитория)

Сборка SPA + **nginx** со встроенным прокси `/api` → сервис `api` в Compose. Откройте интерфейс: **http://localhost:8080** (API напрямую остаётся на **http://localhost:8000**).

```bash
docker compose up --build
```

Отдельная сборка только образа фронтенда:

```bash
docker build -t candy-forecast-frontend ./frontend
```

Переменная `VITE_API_BASE_URL` при сборке образа по умолчанию пустая: запросы идут на тот же origin через nginx. Если нужен абсолютный API URL, передайте build-arg:

```bash
docker build --build-arg VITE_API_BASE_URL=https://api.example.com -t candy-forecast-frontend ./frontend
```

## Переменные окружения

Опционально создайте `.env`:

```env
VITE_API_BASE_URL=https://api.example.com
```

Если `VITE_API_BASE_URL` не задана, фронтенд использует относительные пути и работает через Vite dev-proxy в разработке либо через reverse-proxy в проде.

## Доступные скрипты

- `npm run dev` — dev-сервер с hot reload.
- `npm run build` — type-check + production build в `dist/`.
- `npm run preview` — локальный просмотр прод-сборки.
- `npm run typecheck` — только TypeScript проверка.

## Структура

```
src/
  api/          API client, DTO и функции (auth, stores)
  components/
    auth/       RequireAuth guard
    common/     EmptyState, ErrorState
    layout/     AppShell, PageHeader
    ui/         Кнопки, инпуты, карточки, таблицы и т.п.
  hooks/        React Query / context hooks (useAuth, useStores)
  lib/          Утилиты (cn, format, queryClient)
  pages/        Экраны: Login, Stores, Store, NotFound
  styles/       Глобальные стили Tailwind
```

## Авторизация

- Страница `/login` отправляет POST `/api/v1/auth/login` с `{ username: email, password }`.
- В dev-режиме backend (`AUTH_ENABLED=false`) возвращает 400 на `/auth/login` — фронтенд автоматически делает fallback на `/api/v1/auth/me`, чтобы пустить пользователя как dev-admin.
- Полученный access token сохраняется в `localStorage` и передаётся в `Authorization: Bearer ...`. Cookie `cf_session` тоже отправляется (`credentials: include`).

## Логика подсветки строк

В таблице товаров строка подсвечивается мягким красным (`bg-red-50` / hover `bg-red-100`), если

```
(продажи за последний месяц * 1.2) >= остаток
```

Колонка «Рекомендация» зарезервирована под будущий расчёт.
