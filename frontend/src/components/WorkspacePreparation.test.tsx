import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { User } from "../types/api";
import { WorkspacePreparation } from "./WorkspacePreparation";

const api = vi.hoisted(() => ({
  healthOk: true,
  overviewFails: false,
}));

vi.mock("../api/endpoints", () => ({
  healthApi: {
    get: async () => ({
      status: "ok",
      database: { reader: { ok: api.healthOk, detail: "ok" }, admin: { ok: true, detail: "ok" } },
      llm: { ok: true, provider: "groq", models: ["openai/gpt-oss-120b"], detail: "configured" },
      semantic_layer: { ok: true, measures: 19, dimensions: 12 },
    }),
  },
  queryApi: {
    metadata: async () => ({
      measures: Array.from({ length: 19 }),
      dimensions: Array.from({ length: 12 }),
      coverage: {
        min_date: "2016-09-04",
        max_date: "2018-10-17",
        description: "",
        months: [
          { month: "2016-09", order_count: 4, status: "partial" },
          { month: "2016-10", order_count: 324, status: "full" },
          { month: "2016-11", order_count: 0, status: "none" },
        ],
      },
    }),
    overview: async () => {
      if (api.overviewFails) throw new Error("boom");
      return [{ id: "kpis" }, { id: "monthly_revenue" }];
    },
    suggestions: async () => [],
  },
}));

const user: User = {
  id: 2,
  email: "analyst@demo.com",
  full_name: "Demo Analyst",
  role: "analyst",
  is_active: true,
  created_at: "2026-10-27T10:00:00Z",
};

function renderPrep(onDone: () => void) {
  // reduced motion: steps advance as soon as their real requests finish
  window.matchMedia = ((q: string) => ({
    matches: q.includes("reduce"),
    media: q,
    addEventListener() {},
    removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WorkspacePreparation user={user} onDone={onDone} />
    </QueryClientProvider>,
  );
}

describe("WorkspacePreparation", () => {
  beforeEach(() => {
    api.healthOk = true;
    api.overviewFails = false;
  });

  it("shows real values from the server for each step, then hands over", async () => {
    const onDone = vi.fn();
    renderPrep(onDone);
    expect(screen.getByText("Preparing your workspace")).toBeInTheDocument();
    expect(await screen.findByText("19 metrics · 12 dimensions")).toBeInTheDocument();
    expect(await screen.findByText("2016-09 → 2018-10 · 2 months")).toBeInTheDocument();
    expect(await screen.findByText("groq · openai/gpt-oss-120b")).toBeInTheDocument();
    expect(await screen.findByText("2 widgets ready")).toBeInTheDocument();
    expect(await screen.findByText(/Welcome,/)).toBeInTheDocument();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it("marks a failed step as a warning instead of blocking sign-in", async () => {
    api.overviewFails = true;
    api.healthOk = false;
    const onDone = vi.fn();
    renderPrep(onDone);
    expect(await screen.findByText("Database not reachable")).toBeInTheDocument();
    expect(await screen.findByText("Not available right now")).toBeInTheDocument();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });
});
