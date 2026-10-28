import { useCallback, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { Aurora } from "../components/Aurora";
import { IconDatabase, IconLock, IconShield, IconSparkles, IconTrend } from "../components/Icons";
import { BrandMark, ThemeToggle } from "../components/Layout";
import { WorkspacePreparation } from "../components/WorkspacePreparation";
import { useAuth } from "../hooks/useAuth";
import { useCountUp } from "../hooks/useCountUp";
import type { User } from "../types/api";

const DEMO = [
  { role: "Admin", email: "admin@demo.com", password: "Admin@123", hint: "Users & roles" },
  { role: "Analyst", email: "analyst@demo.com", password: "Analyst@123", hint: "Build dashboards" },
  { role: "Viewer", email: "viewer@demo.com", password: "Viewer@123", hint: "Ask & view" },
];

const FEATURES: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <IconSparkles size={18} />,
    title: "Plain-English questions",
    text: "An AI planner maps your question onto governed business metrics.",
  },
  {
    icon: <IconDatabase size={18} />,
    title: "One semantic layer",
    text: "Every number uses the same definitions - no double counting.",
  },
  {
    icon: <IconShield size={18} />,
    title: "Never guesses",
    text: "Validated, read-only SQL, and an honest refusal when the data can't answer.",
  },
];

function Stat({
  value,
  suffix,
  label,
  delay,
}: {
  value: number;
  suffix: string;
  label: string;
  delay: number;
}) {
  const n = useCountUp(value, 1400, delay);
  return (
    <div className="glass p-4">
      <div className="text-2xl font-bold tabular-nums">
        {Math.round(n)}
        {suffix}
      </div>
      <div className="text-xs text-white/60">{label}</div>
    </div>
  );
}

/** Decorative trend card: an abstract line that draws itself (no data values shown). */
function TrendIllustration() {
  return (
    <div className="glass float-slow w-72 p-4 shadow-2xl">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold text-white/80">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-cyan-400/15 text-cyan-300">
            <IconTrend size={14} />
          </span>
          Monthly trend
        </div>
        <span className="rounded-full bg-emerald-400/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
          validated
        </span>
      </div>
      <svg viewBox="0 0 260 90" className="h-24 w-full" aria-hidden="true">
        <defs>
          <linearGradient id="trend-stroke" x1="0" x2="1">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="60%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
          <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[22, 45, 68].map((y) => (
          <line key={y} x1="0" x2="260" y1={y} y2={y} stroke="rgba(255,255,255,0.08)" />
        ))}
        <path
          d="M0 78 C 20 74, 30 70, 45 62 S 75 58, 90 50 S 120 46, 135 40 S 160 20, 175 14 S 200 24, 215 18 S 240 16, 260 20 L 260 90 L 0 90 Z"
          fill="url(#trend-fill)"
          className="animate-fade-up"
          style={{ animationDelay: "1.2s" }}
        />
        <path
          d="M0 78 C 20 74, 30 70, 45 62 S 75 58, 90 50 S 120 46, 135 40 S 160 20, 175 14 S 200 24, 215 18 S 240 16, 260 20"
          fill="none"
          stroke="url(#trend-stroke)"
          strokeWidth="3"
          strokeLinecap="round"
          className="draw-line"
        />
      </svg>
      <div className="mt-1 flex gap-1.5">
        {["SELECT", "validated", "read-only"].map((t) => (
          <span
            key={t}
            className="rounded-md bg-white/[0.07] px-1.5 py-0.5 font-mono text-[10px] text-white/60"
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  // idle -> signing in -> preparing workspace (animation) -> app
  const [phase, setPhase] = useState<"idle" | "signing" | "preparing">("idle");
  const [signedIn, setSignedIn] = useState<User | null>(null);
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const finish = useCallback(() => navigate(from, { replace: true }), [navigate, from]);

  if (user && phase === "idle") return <Navigate to={from} replace />;
  if (phase === "preparing" && signedIn)
    return <WorkspacePreparation user={signedIn} onDone={finish} />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPhase("signing");
    setError(null);
    try {
      const u = await login(email, password);
      setSignedIn(u);
      setPhase("preparing");
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* Brand panel */}
      <Aurora className="hidden lg:flex lg:flex-col lg:justify-between lg:gap-8 lg:px-12 lg:py-10">
        <div className="flex items-center gap-3 animate-fade-up">
          <BrandMark size={42} />
          <div className="leading-tight">
            <div className="text-lg font-bold tracking-tight">Self-Service BI</div>
            <div className="text-sm text-white/60">Semantic layer · Natural-language queries</div>
          </div>
        </div>

        <div className="relative">
          <div className="max-w-xl animate-fade-up" style={{ animationDelay: "120ms" }}>
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">
              <IconLock size={13} /> Read-only · Validated · Explainable
            </p>
            <h1 className="text-4xl font-extrabold leading-[1.08] tracking-tight xl:text-5xl">
              Ask your data.
              <br />
              <span className="text-aurora">Get answers you can trust.</span>
            </h1>
            <p className="mt-4 max-w-lg text-base leading-relaxed text-white/70">
              Business questions about Brazilian e-commerce, answered with the exact SQL, the
              business definitions used, and every assumption made.
            </p>
            <ul className="mt-7 grid gap-3">
              {FEATURES.map((f, i) => (
                <li
                  key={f.title}
                  className="flex items-start gap-3 animate-fade-up"
                  style={{ animationDelay: `${300 + i * 120}ms` }}
                >
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/30 to-cyan-400/20 text-cyan-200 ring-1 ring-white/15">
                    {f.icon}
                  </span>
                  <div>
                    <p className="font-semibold">{f.title}</p>
                    <p className="text-sm text-white/65">{f.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="flex items-end justify-between gap-6">
          <div
            className="grid w-full max-w-sm grid-cols-3 gap-3 animate-fade-up"
            style={{ animationDelay: "600ms" }}
          >
            <Stat value={99} suffix="K" label="orders analysed" delay={500} />
            <Stat value={27} suffix="" label="Brazilian states" delay={650} />
            <Stat value={100} suffix="%" label="safe refusals" delay={800} />
          </div>
          <div className="hidden xl:block">
            <TrendIllustration />
          </div>
        </div>
      </Aurora>

      {/* Form */}
      <section className="relative flex items-center justify-center px-5 py-12">
        <div className="absolute right-5 top-5">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <BrandMark size={40} />
            <div>
              <div className="text-lg font-bold">Self-Service BI</div>
              <div className="text-sm text-ink-2">Ask the data in plain English</div>
            </div>
          </div>
          <p className="eyebrow">Welcome back</p>
          <h2 className="mt-1 text-3xl font-bold tracking-tight">Sign in to your workspace</h2>
          <p className="mt-2 text-sm text-ink-2">
            Use your account, or pick a demo role below to explore.
          </p>

          <form onSubmit={submit} className="card mt-7 space-y-5 p-6">
            <div>
              <label className="label" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                className="input"
                placeholder="you@company.com"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="input"
                placeholder="••••••••"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && (
              <p
                className="rounded-xl bg-critical-soft px-3 py-2 text-sm text-critical"
                role="alert"
              >
                {error}
              </p>
            )}
            <button
              type="submit"
              className="btn-primary w-full py-2.5 text-[15px]"
              disabled={phase !== "idle"}
            >
              {phase === "signing" ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="mt-6">
            <div className="mb-3 flex items-center gap-3 text-xs font-semibold uppercase tracking-wider text-muted">
              <span className="h-px flex-1 bg-line" />
              Demo accounts
              <span className="h-px flex-1 bg-line" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  aria-label={d.role}
                  className="card-interactive flex flex-col items-start px-3 py-2.5 text-left"
                  onClick={() => {
                    setEmail(d.email);
                    setPassword(d.password);
                  }}
                >
                  <span className="text-sm font-semibold">{d.role}</span>
                  <span className="text-xs text-muted">{d.hint}</span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-center text-xs text-muted">
              Fills the form with a demo user (configured in the backend .env).
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
