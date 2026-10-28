import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../hooks/useAuth";
import type { QueryResponse } from "../types/api";

export function Providers({ children, route = "/" }: { children: ReactNode; route?: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[route]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

export function makeResponse(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    status: "answered",
    question: "Total sales in 2017",
    answer_text: "Total Sales in 2017 was R$ 7,142,672.43.",
    reason: null,
    suggestions: [],
    clarification: null,
    sql: "SELECT SUM(order_revenue) AS total_sales FROM analytics.fact_orders LIMIT 1000",
    data: [{ total_sales: 7142672.43 }],
    columns: [
      {
        name: "total_sales",
        label: "Total Sales",
        role: "measure",
        format: "currency",
        dimension_type: null,
        grain: null,
      },
    ],
    chart: {
      type: "kpi",
      title: "Total Sales",
      x: null,
      y: ["total_sales"],
      series: null,
      reason: "single value",
    },
    explanation: {
      mode: "semantic",
      definitions: [
        {
          name: "total_sales",
          label: "Total Sales",
          definition: "Sum of payments, excluding canceled orders.",
        },
      ],
      business_rules: ["Total Sales: Excludes canceled and unavailable orders."],
      filters: [],
      time_range: "Order date from 2017-01-01 to 2017-12-31",
      sources: ["analytics.fact_orders"],
      notes: [],
    },
    warnings: [],
    assumptions: [],
    confidence: "high",
    plan: { measures: ["total_sales"] },
    steps: [{ name: "understanding", status: "ok", ms: 900, detail: null }],
    row_count: 1,
    truncated: false,
    execution_ms: 1200,
    llm_model: "gemini-test",
    ...overrides,
  };
}
