import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import {
  IconAsk,
  IconBook,
  IconClock,
  IconGrid,
  IconHome,
  IconLogout,
  IconMoon,
  IconShield,
  IconSun,
} from "./Icons";
import { RoleBadge, Spinner } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: IconHome, end: true },
  { to: "/ask", label: "Ask", icon: IconAsk },
  { to: "/dashboards", label: "My Dashboards", icon: IconGrid },
  { to: "/catalog", label: "Data Catalog", icon: IconBook },
  { to: "/history", label: "History", icon: IconClock },
];

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      className="btn-ghost px-2"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? <IconSun /> : <IconMoon />}
    </button>
  );
}

/** Redirects to /login when not signed in. */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Signing in" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Layout />;
}

function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-2 px-5 py-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-ink">
            <IconShield size={18} />
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Self-Service BI</div>
            <div className="text-xs text-muted">Olist · Brazil</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:pb-0" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-accent-soft text-ink"
                    : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-end gap-3 border-b border-line bg-surface px-4 py-2.5 sm:px-8">
          <ThemeToggle />
          <div className="hidden text-right text-sm sm:block">
            <div className="font-medium">{user?.full_name || user?.email}</div>
            <div className="text-xs text-muted">{user?.email}</div>
          </div>
          {user && <RoleBadge role={user.role} />}
          <button
            type="button"
            className="btn-ghost px-2"
            onClick={logout}
            aria-label="Sign out"
            title="Sign out"
          >
            <IconLogout />
          </button>
        </header>
        <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
