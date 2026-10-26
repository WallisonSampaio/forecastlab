/** Thin REST client for the ForecastLab FastAPI backend. */

export type Params = Record<string, string | number | boolean | string[] | undefined | null>;

export const NETWORK_ERROR =
  "Não foi possível conectar à API do ForecastLab. Verifique se o backend está em execução.";

/** HTTP error answered by the API. `message` is always user-facing pt-BR text. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The API could not be reached (server down, wrong URL, CORS, offline, or a proxy's 502/503/504/empty 500). */
export class NetworkError extends Error {
  constructor(message = NETWORK_ERROR) {
    super(message);
    this.name = "NetworkError";
  }
}

/**
 * User-facing pt-BR message for an HTTP error. A backend `detail` string (already pt-BR) always wins;
 * FastAPI's validation list (422) and server errors without a detail get a generic pt-BR text.
 */
export function httpErrorMessage(status: number, detail?: unknown): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (status === 422) return "Parâmetros inválidos.";
  if (status >= 500) return "Erro interno da API.";
  if (status === 404) return "Recurso não encontrado.";
  if (status === 413) return "O arquivo é grande demais para ser enviado.";
  return `A API respondeu com erro (${status}).`;
}

const BASE = import.meta.env.VITE_API_URL ?? "";

export function buildQuery(params?: Params): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => q.append(key, v));
    else q.append(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}${buildQuery(params)}`, {
      method,
      headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new NetworkError();
  }
  if (!res.ok) {
    let text = "";
    let detail: unknown;
    try {
      text = await res.text();
      detail = (JSON.parse(text) as { detail?: unknown } | null)?.detail;
    } catch {
      /* non-JSON error body (e.g. a proxy page or FastAPI's plain-text 500) */
    }
    // A gateway error, or the empty 500 the Vite dev proxy answers when the backend is down, means the API
    // itself could not be reached; FastAPI's own 500 always has a body.
    const unreachable = [502, 503, 504].includes(res.status) || (res.status === 500 && !text.trim());
    if (unreachable && !(typeof detail === "string" && detail.trim())) throw new NetworkError();
    throw new ApiError(res.status, httpErrorMessage(res.status, detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>("GET", path, undefined, params),
  post: <T>(path: string, body?: unknown, params?: Params) => request<T>("POST", path, body ?? {}, params),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  url: (path: string, params?: Params) => `${BASE}${path}${buildQuery(params)}`,
};
