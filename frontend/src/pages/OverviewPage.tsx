import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { ChartView } from "../components/ChartView";
import {
  IconCalendar,
  IconCard,
  IconCart,
  IconLayers,
  IconMapPin,
  IconSearch,
  IconSparkles,
  IconStar,
  IconTag,
  IconTrend,
  IconTruck,
  IconUsers,
  IconWallet,
  IconWarning,
} from "../components/Icons";
import { ErrorNote, Skeleton } from "../components/ui";
import { useIncompleteMonths, useMetadata, useOverview } from "../hooks/queries";
import { useAuth } from "../hooks/useAuth";
import type { OverviewWidget } from "../types/api";
import { formatValue } from "../utils/format";

const KPI_ICON: Record<string, ReactNode> = {
  total_sales: <IconWallet size={20} />,
  order_count: <IconCart size={20} />,
  customer_count: <IconUsers size={20} />,
  average_order_value: <IconTag size={20} />,
  average_rating: <IconStar size={20} />,
  late_delivery_rate: <IconTruck size={20} />,
};

const KPI_NOTE: Record<string, string> = {
  total_sales: "Excl. canceled & unavailable",
  order_count: "All statuses",
  customer_count: "Distinct real customers",
  average_order_value: "Per valid order",
  average_rating: "Customer reviews, 1-5",
  late_delivery_rate: "Of delivered orders",
};

const PANEL_ICON: Record<string, ReactNode> = {
  monthly_revenue: <IconTrend size={18} />,
  top_categories: <IconLayers size={18} />,
  sales_by_state: <IconMapPin size={18} />,
  payment_mix: <IconCard size={18} />,
  rating_distribution: <IconStar size={18} />,
};

const QUICK = [
  "Top 5 categories by revenue in 2018",
  "Monthly orders in 2017",
  "Late delivery rate by customer region",
];

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function Hero() {
  const { user } = useAuth();
  const meta = useMetadata();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const coverage = meta.data?.coverage;
  const name = (user?.full_name || user?.email || "").split(/[\s@]/)[0];
  const ask = (question: string) => navigate(`/ask?q=${encodeURIComponent(question)}`);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) ask(q.trim());
  };
  return (
    <section className="hero-gradient relative overflow-hidden rounded-3xl p-6 text-white shadow-lift sm:p-8 animate-fade-up">
      <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative grid gap-6 lg:grid-cols-[1.3fr_1fr] lg:items-end">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ring-1 ring-white/20">
            <IconSparkles size={13} /> Olist · Brazilian e-commerce
          </p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl">
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p className="mt-2 max-w-xl text-white/80">
            Here is how the business performed. Every figure comes from the governed semantic layer
            - ask anything in plain English to go deeper.
          </p>
          <form
            onSubmit={submit}
            className="mt-5 flex max-w-xl items-center gap-2 rounded-2xl bg-white p-1.5 shadow-lg"
          >
            <span className="pl-2.5 text-slate-400">
              <IconSearch size={18} />
            </span>
            <label htmlFor="hero-ask" className="sr-only">
              Ask a question
            </label>
            <input
              id="hero-ask"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. Total sales in São Paulo in 2018"
              className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
            />
            <button type="submit" className="btn-primary px-4" disabled={!q.trim()}>
              Ask
            </button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {QUICK.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => ask(s)}
                className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-white/20 transition hover:bg-white/20"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        {coverage && (
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "First order", value: coverage.min_date },
              { label: "Last order", value: coverage.max_date },
              { label: "Currency", value: "BRL (R$)" },
              {
                label: "Months with data",
                value: String(coverage.months.filter((m) => m.order_count > 0).length),
              },
            ].map((f) => (
              <div
                key={f.label}
                className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/15 backdrop-blur"
              >
                <div className="flex items-center gap-1.5 text-xs text-white/70">
                  <IconCalendar size={13} />
                  {f.label}
                </div>
                <div className="mt-1 text-lg font-bold tabular-nums">{f.value}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function KpiRow({ widget }: { widget: OverviewWidget }) {
  const r = widget.result;
  const row = r.data[0] ?? {};
  const measures = r.columns.filter((c) => c.role === "measure");
  return (
    <section
      aria-label="Key figures"
      className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6"
    >
      {measures.map((m, i) => (
        <div
          key={m.name}
          className="card-interactive p-4 animate-fade-up"
          style={{ animationDelay: `${i * 40}ms` }}
        >
          <div className="flex items-center justify-between">
            <span className="icon-tile h-9 w-9">
              {KPI_ICON[m.name] ?? <IconSparkles size={18} />}
            </span>
          </div>
          <div className="mt-3 text-[13px] font-medium text-ink-2">{m.label}</div>
          <div
            className="mt-0.5 text-2xl font-bold tabular-nums tracking-tight"
            title={formatValue(row[m.name], m.format)}
          >
            {formatValue(row[m.name], m.format, { compact: true })}
          </div>
          <div className="mt-1 text-xs text-muted">{KPI_NOTE[m.name] ?? "All periods"}</div>
        </div>
      ))}
    </section>
  );
}

function Panel({ widget, className = "" }: { widget: OverviewWidget; className?: string }) {
  const r = widget.result;
  const incompleteMonths = useIncompleteMonths();
  return (
    <section className={`card flex flex-col p-5 animate-fade-up ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="icon-tile h-9 w-9">
            {PANEL_ICON[widget.id] ?? <IconTrend size={18} />}
          </span>
          <div>
            <h2 className="font-semibold leading-tight">{widget.title}</h2>
            <p className="text-xs text-muted">
              {r.explanation.definitions.map((d) => d.label).join(", ")}
            </p>
          </div>
        </div>
        <Link
          to={`/ask?q=${encodeURIComponent(r.question)}`}
          className="rounded-lg px-2 py-1 text-xs font-semibold text-accent-text transition hover:bg-accent-soft"
        >
          Explore →
        </Link>
      </div>
      {r.status === "refused" || r.status === "error" ? (
        <p className="text-sm text-ink-2">{r.reason ?? r.answer_text}</p>
      ) : (
        <ChartView
          type={r.chart?.type ?? "table"}
          columns={r.columns}
          rows={r.data}
          x={r.chart?.x}
          y={r.chart?.y}
          series={r.chart?.series}
          height={260}
          incompleteMonths={incompleteMonths}
        />
      )}
      {r.warnings.length > 0 && (
        <p className="mt-auto flex gap-1.5 pt-3 text-xs text-warn-ink">
          <span className="shrink-0">
            <IconWarning size={14} />
          </span>
          {r.warnings[0]}
        </p>
      )}
    </section>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-64 rounded-3xl" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}

export function OverviewPage() {
  const overview = useOverview();
  if (overview.isLoading) return <OverviewSkeleton />;
  if (overview.error) return <ErrorNote message={errorMessage(overview.error)} />;
  const byId = Object.fromEntries((overview.data ?? []).map((w) => [w.id, w]));
  const kpis = byId.kpis;
  const rules = kpis?.result.explanation.business_rules ?? [];
  return (
    <div className="space-y-6">
      <Hero />
      {kpis && <KpiRow widget={kpis} />}
      {rules[0] && (
        <p className="-mt-2 text-xs text-muted">
          Business rule applied: {rules[0].replace(/^[^:]+:\s*/, "")} All periods (Sep 2016 - Oct
          2018).
        </p>
      )}
      {byId.monthly_revenue && <Panel widget={byId.monthly_revenue} />}
      <div className="grid gap-6 lg:grid-cols-2">
        {byId.top_categories && <Panel widget={byId.top_categories} />}
        {byId.sales_by_state && <Panel widget={byId.sales_by_state} />}
        {byId.payment_mix && <Panel widget={byId.payment_mix} />}
        {byId.rating_distribution && <Panel widget={byId.rating_distribution} />}
      </div>
    </div>
  );
}
