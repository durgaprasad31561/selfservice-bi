/**
 * Shown right after sign-in. Every step is real work, not a timer: it waits for the
 * request it describes (health check, semantic layer, coverage, overview data) and
 * prefetches into the query cache, so the dashboard opens instantly afterwards.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { healthApi, queryApi } from "../api/endpoints";
import type { Health } from "../api/endpoints";
import type { Metadata, OverviewWidget, User } from "../types/api";
import { Aurora } from "./Aurora";
import { IconCheck, IconChart, IconWarning } from "./Icons";

type StepState = "pending" | "active" | "done" | "warning";

interface Step {
  key: string;
  label: string;
  state: StepState;
  detail?: string;
}

const MIN_STEP_MS = 520;
const TIMEOUT_MS = 15_000;

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Race a request against a timeout. The returned promise is marked as handled straight
 * away (steps await it later, possibly after it already failed), and the timer is cleared
 * as soon as the request settles.
 */
function withTimeout<T>(p: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(new Error("timed out")), TIMEOUT_MS);
  });
  const raced = Promise.race([p, timeout]).finally(() => clearTimeout(timer));
  raced.catch(() => undefined); // observed later via Promise.allSettled
  return raced;
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

const PARTICLES = Array.from({ length: 10 }, (_, i) => {
  const angle = (i / 10) * Math.PI * 2;
  return {
    x: Math.round(Math.cos(angle) * 150),
    y: Math.round(Math.sin(angle) * 150),
    delay: (i * 0.28).toFixed(2),
  };
});

function StepIcon({ state }: { state: StepState }): ReactNode {
  if (state === "done")
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300">
        <IconCheck size={14} />
      </span>
    );
  if (state === "warning")
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-400/15 text-amber-300">
        <IconWarning size={13} />
      </span>
    );
  if (state === "active")
    return (
      <span className="flex h-6 w-6 items-center justify-center">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-cyan-300" />
      </span>
    );
  return (
    <span className="flex h-6 w-6 items-center justify-center">
      <span className="h-1.5 w-1.5 rounded-full bg-white/25" />
    </span>
  );
}

export function WorkspacePreparation({ user, onDone }: { user: User; onDone: () => void }) {
  const qc = useQueryClient();
  const firstName = (user.full_name || user.email).split(/[\s@]/)[0];
  const initial = useMemo<Step[]>(
    () => [
      { key: "connect", label: "Connecting to the secure data warehouse", state: "pending" },
      { key: "semantic", label: "Loading the semantic layer", state: "pending" },
      { key: "coverage", label: "Checking data coverage", state: "pending" },
      { key: "ai", label: "Warming up the AI planner", state: "pending" },
      {
        key: "dashboard",
        label: user.role === "admin" ? "Building your admin workspace" : "Building your dashboard",
        state: "pending",
      },
    ],
    [user.role],
  );
  const [steps, setSteps] = useState<Step[]>(initial);
  const [finished, setFinished] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice in development
    started.current = true;
    const minMs = reducedMotion() ? 0 : MIN_STEP_MS;

    // start all real work at once
    const health = withTimeout(healthApi.get());
    const metadata = withTimeout(
      qc.fetchQuery({ queryKey: ["metadata"], queryFn: queryApi.metadata }),
    );
    const overview = withTimeout(
      qc.fetchQuery({ queryKey: ["overview"], queryFn: queryApi.overview }),
    );
    void qc.prefetchQuery({ queryKey: ["suggestions"], queryFn: queryApi.suggestions });

    const update = (key: string, patch: Partial<Step>) =>
      setSteps((prev) => prev.map((s) => (s.key === key ? { ...s, ...patch } : s)));

    const run = async <T,>(
      key: string,
      work: Promise<T>,
      describe: (v: T) => [StepState, string],
    ) => {
      update(key, { state: "active" });
      const [result] = await Promise.allSettled([work, wait(minMs)]);
      if (result.status === "fulfilled") {
        const [state, detail] = describe(result.value);
        update(key, { state, detail });
      } else {
        update(key, { state: "warning", detail: "Not available right now" });
      }
    };

    (async () => {
      await run<Health>("connect", health, (h) =>
        h.database.reader.ok
          ? ["done", "PostgreSQL · read-only role"]
          : ["warning", "Database not reachable"],
      );
      await run<Metadata>("semantic", metadata, (m) => [
        "done",
        `${m.measures.length} metrics · ${m.dimensions.length} dimensions`,
      ]);
      await run<Metadata>("coverage", metadata, (m) => {
        const c = m.coverage;
        if (!c) return ["warning", "Coverage unknown"];
        const months = c.months.filter((x) => x.order_count > 0).length;
        return ["done", `${c.min_date.slice(0, 7)} → ${c.max_date.slice(0, 7)} · ${months} months`];
      });
      await run<Health>("ai", health, (h) =>
        h.llm.ok
          ? ["done", `${h.llm.provider} · ${h.llm.models[0] ?? ""}`]
          : ["warning", "AI model not configured"],
      );
      await run<OverviewWidget[]>("dashboard", overview, (w) => [
        "done",
        `${w.length} widgets ready`,
      ]);
      setFinished(true);
      await wait(reducedMotion() ? 0 : 700);
      onDone();
    })();
  }, [qc, onDone]);

  const complete = steps.filter((s) => s.state === "done" || s.state === "warning").length;
  const pct = Math.round((complete / steps.length) * 100);

  return (
    <div className="fixed inset-0 z-50">
      <Aurora
        as="div"
        className="flex h-full w-full items-center justify-center overflow-y-auto px-5 py-10 animate-fade-up"
      >
        <div className="w-full max-w-xl text-center" role="status" aria-live="polite">
          {/* orbital visual */}
          <div className="relative mx-auto mb-8 h-56 w-56">
            <div className="orbit orbit-spin">
              <span className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-cyan-300 shadow-[0_0_14px_#67e8f9]" />
            </div>
            <div className="orbit orbit-spin-reverse" style={{ inset: "26px" }}>
              <span className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-blue-400 shadow-[0_0_14px_#60a5fa]" />
              <span className="absolute left-0 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-violet-400 shadow-[0_0_12px_#a78bfa]" />
            </div>
            <div className="orbit" style={{ inset: "54px", borderStyle: "dashed" }} />
            <div className="absolute inset-0 flex items-center justify-center">
              {PARTICLES.map((p, i) => (
                <span
                  key={i}
                  className="data-particle"
                  style={
                    {
                      "--x0": `${p.x}px`,
                      "--y0": `${p.y}px`,
                      animationDelay: `${p.delay}s`,
                    } as React.CSSProperties
                  }
                />
              ))}
              <span className="pulse-core flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 via-cyan-400 to-violet-500 text-white">
                {finished ? <IconCheck size={34} /> : <IconChart size={34} />}
              </span>
            </div>
          </div>

          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300/90">
            {finished ? "All set" : "Preparing your workspace"}
          </p>
          <h2 className="mt-2 text-3xl font-extrabold tracking-tight">
            {finished ? (
              <>
                Welcome, <span className="text-aurora">{firstName}</span>
              </>
            ) : (
              <>
                Getting the data ready for <span className="text-aurora">{firstName}</span>
              </>
            )}
          </h2>
          <p className="mt-2 text-sm text-white/65">
            Olist Brazilian e-commerce · semantic layer · read-only access
          </p>

          <div className="glass mt-7 p-2 text-left">
            {steps.map((s) => (
              <div
                key={s.key}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 transition ${
                  s.state === "active" ? "bg-white/[0.07]" : ""
                }`}
              >
                <StepIcon state={s.state} />
                <span
                  className={`flex-1 text-sm ${
                    s.state === "pending" ? "text-white/45" : "font-medium text-white"
                  }`}
                >
                  {s.label}
                </span>
                {s.detail && (
                  <span className="text-right text-xs text-white/60 animate-fade-up">
                    {s.detail}
                  </span>
                )}
              </div>
            ))}
          </div>

          <div className="mt-6">
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="progress-stripes h-full rounded-full transition-[width] duration-500 ease-out"
                style={{ width: `${Math.max(pct, 6)}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-xs text-white/55">
              <span>
                Step {Math.min(complete + 1, steps.length)} of {steps.length}
              </span>
              <span className="tabular-nums">{pct}%</span>
            </div>
          </div>
        </div>
      </Aurora>
    </div>
  );
}
