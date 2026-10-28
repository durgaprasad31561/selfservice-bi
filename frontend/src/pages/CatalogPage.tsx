import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import { IconBook, IconCheck, IconInfo, IconWarning, IconX } from "../components/Icons";
import { ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useMetadata } from "../hooks/queries";
import type { CoverageMonth, Metadata } from "../types/api";
import { formatPeriod } from "../utils/format";
import { normalizeText } from "../components/QuestionBox";

const FORMAT_LABEL: Record<string, string> = {
  currency: "R$ amount",
  integer: "count",
  percent: "percentage",
  days: "days",
  rating: "1–5 rating",
  decimal: "number",
};

const COVERAGE: Record<CoverageMonth["status"], { label: string; cls: string; icon: JSX.Element }> =
  {
    full: {
      label: "Complete",
      cls: "bg-[color:var(--series-1)] text-white",
      icon: <IconCheck size={11} />,
    },
    partial: {
      label: "Incomplete",
      cls: "bg-[color:var(--status-warning)] text-black",
      icon: <IconWarning size={11} />,
    },
    none: { label: "No data", cls: "bg-surface-2 text-muted", icon: <IconX size={11} /> },
  };

function CoverageStrip({ meta }: { meta: Metadata }) {
  const months = (meta.coverage?.months ?? []).filter(
    (m) => m.month >= "2016-09" && m.month <= "2018-10",
  );
  return (
    <section className="card p-5">
      <h2 className="font-semibold">Data coverage</h2>
      <p className="mt-1 text-sm text-ink-2">{meta.coverage?.description}</p>
      <div className="mt-4 grid grid-cols-6 gap-1.5 sm:grid-cols-9 lg:grid-cols-[repeat(26,minmax(0,1fr))]">
        {months.map((m) => {
          const s = COVERAGE[m.status];
          return (
            <div
              key={m.month}
              title={`${formatPeriod(m.month, "month")}: ${m.order_count.toLocaleString("en-US")} orders (${s.label})`}
              className={`flex h-12 flex-col items-center justify-center rounded-md text-[10px] leading-tight ${s.cls}`}
            >
              {s.icon}
              <span>{formatPeriod(m.month, "month").slice(0, 3)}</span>
              <span className="opacity-80">{"\u2019" + m.month.slice(2, 4)}</span>
            </div>
          );
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-4 text-xs text-ink-2">
        {(Object.keys(COVERAGE) as CoverageMonth["status"][]).map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span className={`flex h-4 w-4 items-center justify-center rounded ${COVERAGE[k].cls}`}>
              {COVERAGE[k].icon}
            </span>
            {COVERAGE[k].label}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CatalogPage() {
  const meta = useMetadata();
  const [filter, setFilter] = useState("");
  const f = normalizeText(filter);
  const match = (...texts: string[]) => !f || texts.some((t) => normalizeText(t).includes(f));
  const dimLabel = useMemo(
    () => Object.fromEntries((meta.data?.dimensions ?? []).map((d) => [d.name, d.label])),
    [meta.data],
  );

  if (meta.isLoading) return <Spinner label="Loading catalog" />;
  if (meta.error || !meta.data) return <ErrorNote message={errorMessage(meta.error)} />;
  const m = meta.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Semantic layer"
        icon={<IconBook size={22} />}
        title="Data Catalog"
        subtitle="The semantic layer: every business metric and dimension the system understands, with its exact definition."
        actions={
          <input
            className="input w-64"
            placeholder="Search metrics and dimensions"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Search the catalog"
          />
        }
      />
      <CoverageStrip meta={m} />

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          Metrics <span className="text-sm font-normal text-muted">({m.measures.length})</span>
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {m.measures
            .filter((x) => match(x.label, x.description, ...x.synonyms))
            .map((x) => (
              <article key={x.name} className="card p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="font-semibold">{x.label}</h3>
                  <span className="text-xs text-muted">{FORMAT_LABEL[x.format] ?? x.format}</span>
                </div>
                <p className="mt-1 text-sm text-ink-2">{x.description}</p>
                {x.default_filters.length > 0 && (
                  <p className="mt-2 flex gap-1.5 text-xs text-ink-2">
                    <IconInfo size={14} />
                    {x.default_filters.join(" ")}
                  </p>
                )}
                <p className="mt-2 text-xs text-muted">
                  Also called: {x.synonyms.slice(0, 6).join(", ")}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Split by: {x.valid_dimensions.map((d) => dimLabel[d] ?? d).join(", ")}
                </p>
                <Link
                  to={`/ask?q=${encodeURIComponent(`${x.label} in 2017`)}`}
                  className="mt-2 inline-block text-xs text-accent hover:underline"
                >
                  Try “{x.label} in 2017”
                </Link>
              </article>
            ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          Dimensions <span className="text-sm font-normal text-muted">({m.dimensions.length})</span>
        </h2>
        <div className="card divide-y divide-[color:var(--border)]">
          {m.dimensions
            .filter((d) =>
              match(d.label, d.description, ...d.synonyms, ...(d.values ?? []).slice(0, 80)),
            )
            .map((d) => (
              <details key={d.name} className="group p-4">
                <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3">
                  <span>
                    <span className="font-semibold">{d.label}</span>
                    <span className="ml-2 text-sm text-ink-2">{d.description}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted">
                    {d.type === "time"
                      ? d.grains.join(" · ")
                      : `${d.value_count.toLocaleString("en-US")} values`}
                  </span>
                </summary>
                {d.values && d.values.length > 0 && (
                  <div className="mt-3 flex max-h-48 flex-wrap gap-1.5 overflow-auto">
                    {d.values
                      .slice(0, d.name === "customer_city" || d.name === "seller_city" ? 120 : 200)
                      .map((v) => (
                        <span
                          key={v}
                          className="rounded bg-surface-2 px-2 py-0.5 text-xs text-ink-2"
                        >
                          {v}
                        </span>
                      ))}
                    {d.values.length > 120 &&
                      (d.name === "customer_city" || d.name === "seller_city") && (
                        <span className="px-2 py-0.5 text-xs text-muted">
                          …and {d.values.length - 120} more
                        </span>
                      )}
                  </div>
                )}
              </details>
            ))}
        </div>
      </section>

      <section className="card p-5">
        <h2 className="font-semibold">Not in the data</h2>
        <p className="mt-1 text-sm text-ink-2">
          Questions about these are answered with “I don’t have sufficient data” and the reason
          below.
        </p>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {m.unsupported_concepts.map((u) => (
            <li key={u.name} className="rounded-lg bg-surface-2 p-3 text-sm">
              <span className="font-medium capitalize">{u.name.replace(/_/g, " ")}</span>
              <span className="block text-ink-2">{u.reason}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
