/**
 * API base URL for the browser.
 * - undefined (local dev, no .env): http://localhost:8000 — прямой вызов API.
 * - пустая строка (Docker): относительные пути `/v1/...` — прокси через Next.js → сервис `api`.
 */
const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
const API_BASE_URL =
  raw === undefined
    ? "http://localhost:8000".replace(/\/$/, "")
    : raw.trim() === ""
      ? ""
      : raw.replace(/\/$/, "");

export type ApiError = {
  status: number;
  message: string;
};

export class ApiRequestError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiRequestError";
  }
}

export function apiUrl(path: string): string {
  if (path.startsWith("http")) return path;
  if (!API_BASE_URL) return path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function apiFetchJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = apiUrl(path);
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers,
  });
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const msg =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : typeof body === "string"
          ? body
          : res.statusText;
    throw new ApiRequestError(res.status, msg || "Request failed");
  }
  return body as T;
}
