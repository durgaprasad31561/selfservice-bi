import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { IconDatabase, IconLock, IconShield, IconSparkles } from "../components/Icons";
import { BrandMark, ThemeToggle } from "../components/Layout";
import { useAuth } from "../hooks/useAuth";

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
    text: "Every number uses the same definitions: no double counting, ever.",
  },
  {
    icon: <IconShield size={18} />,
    title: "Never guesses",
    text: "Validated, read-only SQL - and an honest refusal when the data can't answer.",
  },
];

const STATS = [
  { value: "99K", label: "orders" },
  { value: "27", label: "states" },
  { value: "100%", label: "safe refusals" },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <section className="hero-gradient relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25 backdrop-blur">
            <BrandMark size={30} />
          </span>
          <div className="leading-tight">
            <div className="text-lg font-bold tracking-tight">Self-Service BI</div>
            <div className="text-sm text-white/70">Semantic layer · Natural-language queries</div>
          </div>
        </div>

        <div className="relative max-w-lg">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ring-1 ring-white/20">
            <IconLock size={13} /> Read-only · Validated · Explainable
          </p>
          <h1 className="text-4xl font-extrabold leading-[1.1] tracking-tight xl:text-5xl">
            Ask your data.
            <br />
            Get answers you can trust.
          </h1>
          <p className="mt-4 text-base text-white/80">
            Business questions about Brazilian e-commerce, answered with the exact SQL, the business
            definitions used, and every assumption made.
          </p>
          <ul className="mt-8 space-y-4">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-3">
                <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/20">
                  {f.icon}
                </span>
                <div>
                  <p className="font-semibold">{f.title}</p>
                  <p className="text-sm text-white/75">{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative grid max-w-md grid-cols-3 gap-3">
          {STATS.map((s) => (
            <div
              key={s.label}
              className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/15 backdrop-blur"
            >
              <div className="text-2xl font-bold tabular-nums">{s.value}</div>
              <div className="text-xs text-white/70">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

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
            <button type="submit" className="btn-primary w-full py-2.5 text-[15px]" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
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
