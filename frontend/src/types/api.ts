/** Types mirroring the FastAPI response models (backend/app/schemas). */

export type Role = "admin" | "analyst" | "viewer";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type Status = "answered" | "answered_with_warning" | "refused" | "clarify" | "error";
export type Confidence = "high" | "medium" | "low";
export type ChartType = "kpi" | "line" | "bar" | "pie" | "table";
export type ValueFormat = "currency" | "integer" | "decimal" | "percent" | "days" | "rating";

export interface ColumnInfo {
  name: string;
  label: string;
  role: "dimension" | "measure" | "column";
  format: ValueFormat | null;
  dimension_type: "time" | "categorical" | null;
  grain: string | null;
}

export interface ChartSpec {
  type: ChartType;
  title: string;
  x: string | null;
  y: string[];
  series: string | null;
  reason: string;
}

export interface Explanation {
  mode: "semantic" | "custom_sql" | "none";
  definitions: { name: string; label: string; definition: string }[];
  business_rules: string[];
  filters: string[];
  time_range: string | null;
  sources: string[];
  notes: string[];
}

export interface PipelineStep {
  name: string;
  status: "ok" | "warning" | "failed" | "skipped";
  ms: number;
  detail: string | null;
}

export type Row = Record<string, string | number | null>;

export interface QueryResponse {
  status: Status;
  question: string;
  answer_text: string;
  reason: string | null;
  suggestions: string[];
  clarification: { question: string; options: string[] } | null;
  sql: string | null;
  data: Row[];
  columns: ColumnInfo[];
  chart: ChartSpec | null;
  explanation: Explanation;
  warnings: string[];
  assumptions: string[];
  confidence: Confidence;
  plan: Record<string, unknown> | null;
  steps: PipelineStep[];
  row_count: number;
  truncated: boolean;
  execution_ms: number;
  llm_model: string | null;
}

export interface MeasureMeta {
  name: string;
  label: string;
  description: string;
  type: string;
  format: ValueFormat;
  synonyms: string[];
  valid_dimensions: string[];
  default_filters: string[];
}

export interface DimensionMeta {
  name: string;
  label: string;
  description: string;
  type: "time" | "categorical";
  synonyms: string[];
  grains: string[];
  value_count: number;
  values?: string[];
}

export interface CoverageMonth {
  month: string;
  order_count: number;
  status: "full" | "partial" | "none";
}

export interface Metadata {
  name: string;
  description: string;
  currency: string;
  country: string;
  measures: MeasureMeta[];
  dimensions: DimensionMeta[];
  coverage: {
    min_date: string;
    max_date: string;
    description: string;
    months: CoverageMonth[];
  } | null;
  unsupported_concepts: { name: string; reason: string; suggestion: string | null }[];
}

export interface Suggestion {
  question: string;
  category: string;
}

export interface OverviewWidget {
  id: string;
  title: string;
  result: QueryResponse;
}

export interface Dashboard {
  id: number;
  name: string;
  description: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
  widget_count: number;
  can_edit: boolean;
}

export interface Widget {
  id: number;
  dashboard_id: number;
  title: string;
  question: string;
  mode: "semantic" | "custom_sql";
  chart_type: ChartType | null;
  position: number;
  created_at: string;
  result: QueryResponse | null;
}

export interface DashboardDetail extends Dashboard {
  widgets: Widget[];
}

export interface HistoryItem {
  id: number;
  user_id: number;
  question: string;
  status: Status;
  answer_text: string;
  reason: string | null;
  sql: string | null;
  confidence: Confidence | null;
  mode: string | null;
  row_count: number;
  execution_ms: number;
  llm_model: string | null;
  created_at: string;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  limit: number;
  offset: number;
}
