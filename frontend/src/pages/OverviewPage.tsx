import { Link } from "react-router-dom";
import { ChartView } from "../components/ChartView";
import { IconWarning } from "../components/Icons";
import { ErrorNote, PageHeader, Spinner } from "../components/ui";
import { errorMessage } from "../api/client";
import { useIncompleteMonths, useOverview } from "../hooks/queries";
import type { OverviewWidget } from "../types/api";
import { formatValue } from "../utils/format";

function KpiRow({ widget }: { widget: OverviewWidget }) {
  const r = widget.result;
  const row = r.data[0] ?? {};
  const measures = r.columns.filter((c) => c.role === "measure");
  return (
    <section
      aria-label="Key figures"
      className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
    >
      {measures.map((m) => (
        <div key={m.name} className="card p-4">
          <div className="text-xs font-medium text-ink-2">{m.label}</div>
          <div
            className="mt-1 text-2xl font-semibold tabular-nums tracking-tight"
            title={formatValue(row[m.name], m.format)}
          >
            {formatValue(row[m.name], m.format, { compact: true })}
          </div>
        </div>
      ))}
    </section>
  );
}

function Panel({ widget, className = "" }: { widget: OverviewWidget; className?: string }) {
  const r = widget.result;
  const incompleteMonths = useIncompleteMonths();
  return (
    <section className={`card p-5 ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{widget.title}</h2>
          <p className="text-xs text-muted">
            {r.explanation.definitions.map((d) => d.label).join(", ")}
          </p>
        </div>
        <Link
          to={`/ask?q=${encodeURIComponent(r.question)}`}
          className="text-xs text-accent hover:underline"
        >
          Ask
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
        <p className="mt-3 flex gap-1.5 text-xs text-warn-ink">
          <span className="shrink-0">
            <IconWarning size={14} />
          </span>
          {r.warnings[0]}
        </p>
      )}
    </section>
  );
}

export function OverviewPage() {
  const overview = useOverview();
  if (overview.isLoading) return <Spinner label="Loading overview" />;
  if (overview.error) return <ErrorNote message={errorMessage(overview.error)} />;
  const byId = Object.fromEntries((overview.data ?? []).map((w) => [w.id, w]));
  const kpis = byId.kpis;
  const rules = kpis?.result.explanation.business_rules ?? [];
  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        subtitle={
          <>All figures from the semantic layer, all periods. {rules[0] ? `${rules[0]}` : ""}</>
        }
        actions={
          <Link to="/ask" className="btn-primary">
            Ask a question
          </Link>
        }
      />
      {kpis && <KpiRow widget={kpis} />}
      {byId.monthly_revenue && <Panel widget={byId.monthly_revenue} />}
      <div className="grid gap-5 lg:grid-cols-2">
        {byId.top_categories && <Panel widget={byId.top_categories} />}
        {byId.sales_by_state && <Panel widget={byId.sales_by_state} />}
        {byId.payment_mix && <Panel widget={byId.payment_mix} />}
        {byId.rating_distribution && <Panel widget={byId.rating_distribution} />}
      </div>
    </div>
  );
}
