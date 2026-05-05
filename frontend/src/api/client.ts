const ACCESS_TOKEN_STORAGE_KEY = "candy_forecast.access_token";

const rawBase = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
const API_BASE = rawBase.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly payload: unknown;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      requestId?: string;
      payload?: unknown;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.payload = options.payload;
  }
}

interface RequestOptions {
  method?: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token) {
      window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    }
  } catch {
    // localStorage unavailable; ignore
  }
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) {
    return url;
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    params.append(key, String(value));
  }
  const queryString = params.toString();
  return queryString ? `${url}?${queryString}` : url;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const errorBlock =
      payload && typeof payload === "object" && "error" in payload
        ? (payload as { error?: { message?: unknown; code?: unknown; request_id?: unknown } }).error
        : undefined;

    const rawMessage = errorBlock?.message;
    const message =
      typeof rawMessage === "string"
        ? rawMessage
        : Array.isArray(rawMessage)
          ? rawMessage
              .map((item) =>
                typeof item === "object" && item && "msg" in item
                  ? String((item as { msg: unknown }).msg)
                  : JSON.stringify(item),
              )
              .join("; ")
          : response.statusText || "Request failed";

    throw new ApiError(message, {
      status: response.status,
      code: typeof errorBlock?.code === "string" ? errorBlock.code : undefined,
      requestId:
        typeof errorBlock?.request_id === "string" ? errorBlock.request_id : undefined,
      payload,
    });
  }

  return (payload ?? (undefined as unknown)) as T;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", query, body, signal, headers } = options;
  const url = buildUrl(path, query);

  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };
  if (body !== undefined) {
    finalHeaders["Content-Type"] = finalHeaders["Content-Type"] ?? "application/json";
  }
  const token = getAccessToken();
  if (token && !finalHeaders.Authorization) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("Не удалось связаться с сервером", {
      status: 0,
      code: "network_error",
      payload: error,
    });
  }

  return parseResponse<T>(response);
}
