import { useEffect, useState } from "react";
import type { PipelineStep } from "../types/api";
import { IconCheck, IconWarning, IconX } from "./Icons";

export const STEP_LABELS: Record<string, string> = {
  understanding: "Understanding",
  generating_sql: "Generating SQL",
  validating: "Validating",
  running: "Running",
  checking_results: "Checking results",
};
const ORDER = Object.keys(STEP_LABELS);

/** While a question is running: steps advance with elapsed time (the server reports the real
 *  steps when it answers — see StepTrail). */
export function PipelineProgress() {
  const [active, setActive] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setActive((a) => Math.min(a + 1, ORDER.length - 1)), 1600);
    return () => clearInterval(timer);
  }, []);
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
      {ORDER.map((s, i) => (
        <li key={s} className="flex items-center gap-2">
          <span
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
              i < active
                ? "border-line text-ink-2"
                : i === active
                  ? "border-accent text-ink"
                  : "border-line text-muted"
            }`}
          >
            {i < active ? (
              <IconCheck size={14} />
            ) : i === active ? (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-accent" />
            ) : (
              <span className="h-1.5 w-1.5 rounded-full bg-grid" />
            )}
            {STEP_LABELS[s]}
          </span>
          {i < ORDER.length - 1 && (
            <span className="text-muted" aria-hidden="true">
              →
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

/** The steps the server actually ran, with timings. */
export function StepTrail({ steps }: { steps: PipelineStep[] }) {
  if (!steps.length) return null;
  return (
    <ol className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
      {steps.map((s, i) => (
        <li
          key={`${s.name}-${i}`}
          className="flex items-center gap-1"
          title={s.detail ?? undefined}
        >
          {s.status === "ok" && <IconCheck size={12} />}
          {s.status === "warning" && (
            <span className="text-warn-ink">
              <IconWarning size={12} />
            </span>
          )}
          {s.status === "failed" && (
            <span className="text-critical">
              <IconX size={12} />
            </span>
          )}
          {s.status === "skipped" && <span>–</span>}
          {STEP_LABELS[s.name] ?? s.name}
          <span className="tabular-nums">{s.ms} ms</span>
        </li>
      ))}
    </ol>
  );
}
