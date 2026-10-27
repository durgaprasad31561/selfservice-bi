/** Small shared UI pieces: spinner, badges, empty state, page header. */
import type { ReactNode } from "react";
import type { Confidence, Status } from "../types/api";
import { IconCheck, IconInfo, IconWarning, IconX } from "./Icons";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </span>
  );
}

const STATUS: Record<Status, { label: string; icon: ReactNode; cls: string }> = {
  answered: { label: "Answered", icon: <IconCheck size={14} />, cls: "text-good" },
  answered_with_warning: { label: "Answered with warning", icon: <IconWarning size={14} />, cls: "text-warn-ink" },
  refused: { label: "Not enough data", icon: <IconInfo size={14} />, cls: "text-ink-2" },
  clarify: { label: "Needs clarification", icon: <IconInfo size={14} />, cls: "text-accent" },
  error: { label: "Error", icon: <IconX size={14} />, cls: "text-critical" },
};

/** Status always shown as icon + label, never colour alone. */
export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs font-medium ${s.cls}`}>
      {s.icon}
      {s.label}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const bars = confidence === "high" ? 3 : confidence === "medium" ? 2 : 1;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs text-ink-2"
      title="How sure the system is that this answers your question as intended"
    >
      <span className="flex items-end gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={`w-1 rounded-sm ${i <= bars ? "bg-ink-2" : "bg-grid"}`}
            style={{ height: 4 + i * 3 }}
          />
        ))}
      </span>
      {confidence[0].toUpperCase() + confidence.slice(1)} confidence
    </span>
  );
}

export function RoleBadge({ role }: { role: string }) {
  return (
    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-2">
      {role}
    </span>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center px-6 py-12 text-center">
      <p className="text-base font-medium">{title}</p>
      {children && <div className="mt-2 max-w-md text-sm text-ink-2">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="card flex items-start gap-2 border-line p-4 text-sm" role="alert">
      <span className="text-critical"><IconX /></span>
      <span>{message}</span>
    </div>
  );
}
