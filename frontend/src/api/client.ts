import axios, { AxiosError } from "axios";

/** Axios instance for the FastAPI backend (proxied at /api by Vite in development). */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "",
  timeout: 120_000,
});

const TOKEN_KEY = "bi.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session lasts until reload */
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
      setToken(null);
      onUnauthorized?.();
    }
    return Promise.reject(error);
  },
);

/** Human-readable message from an API error. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((d: { field?: string; message?: string }) =>
          d.field ? `${d.field}: ${d.message}` : d.message,
        )
        .join("; ");
    }
    if (error.code === "ECONNABORTED") return "The request timed out. Please try again.";
    if (!error.response) return "Cannot reach the server. Is the backend running on port 8000?";
    return `Request failed (${error.response.status}).`;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}
