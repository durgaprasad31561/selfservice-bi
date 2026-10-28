import { api } from "./client";
import type {
  ChartType,
  Dashboard,
  DashboardDetail,
  HistoryPage,
  Metadata,
  OverviewWidget,
  QueryResponse,
  Role,
  Suggestion,
  TokenResponse,
  User,
  Widget,
} from "../types/api";

export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>("/api/auth/login", { email, password }).then((r) => r.data),
  register: (email: string, password: string, full_name: string) =>
    api.post<User>("/api/auth/register", { email, password, full_name }).then((r) => r.data),
  me: () => api.get<User>("/api/auth/me").then((r) => r.data),
};

export const queryApi = {
  ask: (question: string) =>
    api.post<QueryResponse>("/api/query", { question }).then((r) => r.data),
  metadata: () => api.get<Metadata>("/api/metadata").then((r) => r.data),
  suggestions: () =>
    api.get<{ suggestions: Suggestion[] }>("/api/suggestions").then((r) => r.data.suggestions),
  overview: () =>
    api.get<{ widgets: OverviewWidget[] }>("/api/overview").then((r) => r.data.widgets),
};

export interface PinRequest {
  title: string;
  question: string;
  mode: "semantic" | "custom_sql";
  plan?: Record<string, unknown> | null;
  custom_sql?: string | null;
  chart_type?: ChartType | null;
}

export const dashboardApi = {
  list: () => api.get<Dashboard[]>("/api/dashboards").then((r) => r.data),
  get: (id: number) => api.get<DashboardDetail>(`/api/dashboards/${id}`).then((r) => r.data),
  create: (name: string, description = "") =>
    api.post<Dashboard>("/api/dashboards", { name, description }).then((r) => r.data),
  update: (id: number, body: { name?: string; description?: string }) =>
    api.patch<Dashboard>(`/api/dashboards/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/api/dashboards/${id}`),
  addWidget: (id: number, body: PinRequest) =>
    api.post<Widget>(`/api/dashboards/${id}/widgets`, body).then((r) => r.data),
  updateWidget: (id: number, widgetId: number, body: { title?: string; chart_type?: ChartType }) =>
    api.patch<Widget>(`/api/dashboards/${id}/widgets/${widgetId}`, body).then((r) => r.data),
  removeWidget: (id: number, widgetId: number) =>
    api.delete(`/api/dashboards/${id}/widgets/${widgetId}`),
};

export const historyApi = {
  list: (params: { limit?: number; offset?: number; status?: string; all_users?: boolean } = {}) =>
    api.get<HistoryPage>("/api/history", { params }).then((r) => r.data),
  remove: (id: number) => api.delete(`/api/history/${id}`),
};

export const adminApi = {
  users: () => api.get<User[]>("/api/auth/users").then((r) => r.data),
  createUser: (body: { email: string; password: string; full_name: string; role: Role }) =>
    api.post<User>("/api/auth/register", body).then((r) => r.data),
  updateUser: (id: number, body: { role?: Role; is_active?: boolean; full_name?: string }) =>
    api.patch<User>(`/api/auth/users/${id}`, body).then((r) => r.data),
};
