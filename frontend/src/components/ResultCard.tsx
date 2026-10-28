import { useState } from "react";
import type { ReactNode } from "react";
import { useIncompleteMonths } from "../hooks/queries";
import { useAuth } from "../hooks/useAuth";
import type { ChartType, QueryResponse } from "../types/api";
import { downloadCsv, slugify } from "../utils/csv";
import { ChartView } from "./ChartView";
import {
  IconSparkles,
  IconChart,
  IconCode,
  IconDownload,
  IconInfo,
  IconPin,
  IconTable,
  IconWarning,
  IconX,
} from "./Icons";
import { PinDialog } from "./PinDialog";
import { StepTrail } from "./PipelineProgress";
import { SqlPanel } from "./SqlPanel";
import { ConfidenceBadge, StatusBadge } from "./ui";

interface Props {
  response: QueryResponse;
  onAsk?: (question: string) => void;
  showActions?: boolean;
}

function Disclosure({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-lg border border-line">
      <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-sm font-medium text-ink-2 hover:text-ink">
        {icon}
        {title}
        <span
          className="ml-auto text-muted transition-transform group-open:rotate-90"
          aria-hidden="true"
        >
          ›
        </span>
      </summary>
      <div className="border-t border-line p-3 text-sm">{children}</div>
    </details>
  );
}

export function WarningBanner({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <div
      className="flex gap-3 rounded-lg border border-[color:var(--status-warning)] bg-warn-soft p-3 text-sm text-warn-ink"
      role="note"
    >
      <span className="mt-0.5 shrink-0">
        <IconWarning />
      </span>
      <div>
        <p className="font-semibold">Read with care</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function SuggestionList({ items, onAsk }: { items: string[]; onAsk?: (q: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="mt-3">
      <p className="label">Suggestions</p>
      <ul className="space-y-1">
        {items.map((s) => (
          <li key={s} className="text-sm text-ink-2">
            {/^(for example|try|ask)/i.test(s) || !onAsk ? (
              s
            ) : (
              <button
                type="button"
                className="text-left text-accent hover:underline"
                onClick={() => onAsk(s)}
              >
                {s}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Explanation({ r }: { r: QueryResponse }) {
  const e = r.explanation;
  return (
    <div className="space-y-3">
      {e.definitions.length > 0 && (
        <div>
          <p className="label">Business definitions (semantic layer)</p>
          <dl className="space-y-1.5">
            {e.definitions.map((d) => (
              <div key={d.name}>
                <dt className="font-medium">{d.label}</dt>
                <dd className="text-ink-2">{d.definition}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {e.business_rules.length > 0 && (
        <div>
          <p className="label">Rules applied</p>
          <ul className="list-disc pl-4 text-ink-2">
            {e.business_rules.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      )}
      {(e.filters.length > 0 || e.time_range) && (
        <div>
          <p className="label">Filters</p>
          <ul className="list-disc pl-4 text-ink-2">
            {e.filters.map((f) => (
              <li key={f}>{f}</li>
            ))}
            {e.time_range && <li>{e.time_range}</li>}
          </ul>
        </div>
      )}
      {r.assumptions.length > 0 && (
        <div>
          <p className="label">Assumptions</p>
          <ul className="list-disc pl-4 text-ink-2">
            {r.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {e.notes.length > 0 && (
        <ul className="list-disc pl-4 text-ink-2">
          {e.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {e.sources.length > 0 && (
        <p className="text-xs text-muted">Source tables: {e.sources.join(", ")}</p>
      )}
    </div>
  );
}

export function ResultCard({ response: r, onAsk, showActions = true }: Props) {
  const { canEditDashboards } = useAuth();
  const incompleteMonths = useIncompleteMonths();
  const [view, setView] = useState<"chart" | "table">("chart");
  const [pinning, setPinning] = useState(false);
  const [pinnedTo, setPinnedTo] = useState<string | null>(null);
  const chartType: ChartType = r.chart?.type ?? "table";
  const answered = r.status === "answered" || r.status === "answered_with_warning";

  return (
    <article className="card overflow-hidden">
      <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface-2 px-5 py-3.5">
        <span className="icon-tile h-8 w-8">
          <IconSparkles size={16} />
        </span>
        <h2 className="mr-auto text-[15px] font-semibold">{r.question}</h2>
        <StatusBadge status={r.status} />
        {answered && <ConfidenceBadge confidence={r.confidence} />}
      </header>

      <div className="space-y-4 p-5">
        {r.status === "refused" && (
          <div className="rounded-lg bg-info-soft p-4">
            <div className="flex gap-3">
              <span className="mt-0.5 text-ink-2">
                <IconInfo />
              </span>
              <div>
                <p className="font-semibold">{r.answer_text}</p>
                {r.reason && <p className="mt-1 text-sm text-ink-2">{r.reason}</p>}
                <SuggestionList items={r.suggestions} onAsk={onAsk} />
              </div>
            </div>
          </div>
        )}

        {r.status === "error" && (
          <div className="flex gap-3 rounded-lg border border-line p-4" role="alert">
            <span className="text-critical">
              <IconX />
            </span>
            <div>
              <p className="font-semibold">Something went wrong</p>
              <p className="text-sm text-ink-2">{r.answer_text}</p>
            </div>
          </div>
        )}

        {r.status === "clarify" && r.clarification && (
          <div className="rounded-lg bg-accent-soft p-4">
            <p className="font-semibold">{r.clarification.question || r.answer_text}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {r.clarification.options.map((o) => (
                <button
                  key={o}
                  type="button"
                  className="btn-outline bg-surface"
                  onClick={() => onAsk?.(o)}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>
        )}

        {answered && (
          <>
            <p className="text-xl font-semibold leading-snug tracking-tight">{r.answer_text}</p>
            <WarningBanner warnings={r.warnings} />
            <div>
              {chartType !== "table" && chartType !== "kpi" && (
                <div
                  className="mb-3 inline-flex rounded-lg border border-line p-0.5 text-sm"
                  role="group"
                  aria-label="View"
                >
                  <button
                    type="button"
                    onClick={() => setView("chart")}
                    aria-pressed={view === "chart"}
                    className={`btn px-2.5 py-1 ${view === "chart" ? "bg-surface-2 text-ink" : "text-muted"}`}
                  >
                    <IconChart size={15} /> Chart
                  </button>
                  <button
                    type="button"
                    onClick={() => setView("table")}
                    aria-pressed={view === "table"}
                    className={`btn px-2.5 py-1 ${view === "table" ? "bg-surface-2 text-ink" : "text-muted"}`}
                  >
                    <IconTable size={15} /> Table
                  </button>
                </div>
              )}
              <ChartView
                type={view === "table" ? "table" : chartType}
                columns={r.columns}
                rows={r.data}
                x={r.chart?.x}
                y={r.chart?.y}
                series={r.chart?.series}
                incompleteMonths={incompleteMonths}
              />
            </div>
          </>
        )}

        {(answered || (r.sql && r.status === "refused")) && (
          <div className="space-y-2">
            {r.sql && (
              <Disclosure title="Show SQL" icon={<IconCode size={16} />}>
                <SqlPanel sql={r.sql} />
              </Disclosure>
            )}
            {answered && (
              <Disclosure title="How this was calculated" icon={<IconInfo size={16} />}>
                <Explanation r={r} />
              </Disclosure>
            )}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-3">
        <StepTrail steps={r.steps} />
        <span className="text-xs text-muted tabular-nums">
          total {r.execution_ms} ms{r.llm_model ? ` · ${r.llm_model}` : ""}
        </span>
        {showActions && answered && (
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              className="btn-ghost px-2.5 py-1.5"
              onClick={() => downloadCsv(`${slugify(r.question)}.csv`, r.columns, r.data)}
            >
              <IconDownload size={16} /> Export CSV
            </button>
            {canEditDashboards && (
              <button
                type="button"
                className="btn-outline px-2.5 py-1.5"
                onClick={() => setPinning(true)}
              >
                <IconPin size={16} /> {pinnedTo ? `Pinned to ${pinnedTo}` : "Pin to dashboard"}
              </button>
            )}
          </div>
        )}
      </footer>
      {pinning && (
        <PinDialog
          response={r}
          onClose={() => setPinning(false)}
          onPinned={(name) => {
            setPinnedTo(name);
            setPinning(false);
          }}
        />
      )}
    </article>
  );
}
