/** Small shared UI pieces: spinner, badges, avatar, empty state, page header. */
import type { ReactNode } from "react";
import type { Confidence, Status } from "../types/api";
import { IconCheck, IconInfo, IconSparkles, IconWarning, IconX } from "./Icons";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2.5 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </span>
  );
}

/** Placeholder blocks shown while data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-xl bg-surface-2 ${className}`} aria-hidden="true" />
  );
}

const STATUS: Record<Status, { label: string; icon: ReactNode; cls: string }> = {
  answered: {
    label: "Answered",
    icon: <IconCheck size={13} />,
    cls: "bg-good-soft text-good-ink border-transparent",
  },
  answered_with_warning: {
    label: "Answered with warning",
    icon: <IconWarning size={13} />,
    cls: "bg-warn-soft text-warn-ink border-transparent",
  },
  refused: {
    label: "Not enough data",
    icon: <IconInfo size={13} />,
    cls: "bg-info-soft text-ink-2 border-line",
  },
  clarify: {
    label: "Needs clarification",
    icon: <IconInfo size={13} />,
    cls: "bg-accent-soft text-accent-text border-transparent",
  },
  error: {
    label: "Error",
    icon: <IconX size={13} />,
    cls: "bg-critical-soft text-critical border-transparent",
  },
};

/** Status always shown as icon + label, never colour alone. */
export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status];
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold ${s.cls}`}
    >
      {s.icon}
      {s.label}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const bars = confidence === "high" ? 3 : confidence === "medium" ? 2 : 1;
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-2"
      title="How sure the system is that this answers your question as intended"
    >
      <span className="flex items-end gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={`w-1 rounded-sm ${i <= bars ? "bg-accent" : "bg-grid"}`}
            style={{ height: 4 + i * 3 }}
          />
        ))}
      </span>
      {confidence[0].toUpperCase() + confidence.slice(1)} confidence
    </span>
  );
}

const ROLE_CLS: Record<string, string> = {
  admin: "bg-accent-soft text-accent-text",
  analyst: "bg-good-soft text-good-ink",
  viewer: "bg-surface-2 text-ink-2",
};

export function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${ROLE_CLS[role] ?? ROLE_CLS.viewer}`}
    >
      {role}
    </span>
  );
}

/** Initials in a gradient circle. */
export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const initials =
    name
      .replace(/@.*/, "")
      .split(/[\s._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?";
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 font-semibold text-white"
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

export function EmptyState({
  title,
  children,
  icon,
}: {
  title: string;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center px-6 py-14 text-center">
      <span className="icon-tile mb-4 h-12 w-12">{icon ?? <IconSparkles size={22} />}</span>
      <p className="text-base font-semibold">{title}</p>
      {children && <div className="mt-2 max-w-md text-sm text-ink-2">{children}</div>}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
  icon,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4 animate-fade-up">
      <div className="flex items-start gap-4">
        {icon && <span className="icon-tile mt-1 hidden h-12 w-12 sm:inline-flex">{icon}</span>}
        <div>
          {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
          <h1 className="text-[1.75rem] font-bold leading-tight tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1.5 max-w-3xl text-sm text-ink-2">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      className="flex items-start gap-3 rounded-2xl border border-line bg-critical-soft p-4 text-sm"
      role="alert"
    >
      <span className="mt-0.5 text-critical">
        <IconX />
      </span>
      <span>{message}</span>
    </div>
  );
}
