import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useMetadata } from "../hooks/queries";
import { useTheme } from "../hooks/useTheme";
import {
  IconAsk,
  IconBook,
  IconChart,
  IconClock,
  IconGrid,
  IconHome,
  IconLogout,
  IconMoon,
  IconSearch,
  IconSun,
  IconUsers,
} from "./Icons";
import { Avatar, RoleBadge, Spinner } from "./ui";

type NavItem = {
  to: string;
  label: string;
  icon: typeof IconHome;
  end?: boolean;
  section: "Analytics" | "Data" | "Administration";
};

const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: IconHome, end: true, section: "Analytics" },
  { to: "/ask", label: "Ask", icon: IconAsk, section: "Analytics" },
  { to: "/dashboards", label: "My Dashboards", icon: IconGrid, section: "Analytics" },
  { to: "/catalog", label: "Data Catalog", icon: IconBook, section: "Data" },
  { to: "/history", label: "History", icon: IconClock, section: "Data" },
];

const ADMIN_NAV: NavItem = {
  to: "/admin",
  label: "Admin",
  icon: IconUsers,
  section: "Administration",
};

/** Navigation for a role: admins also get the Admin page. */
export function navItemsFor(role: string | undefined): NavItem[] {
  if (role === "admin") return [...NAV, ADMIN_NAV];
  // viewers cannot own dashboards, so "My" would be misleading
  if (role === "viewer") {
    return NAV.map((n) => (n.to === "/dashboards" ? { ...n, label: "Dashboards" } : n));
  }
  return NAV;
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      className={`btn-ghost h-9 w-9 rounded-full p-0 ${className}`}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? <IconSun /> : <IconMoon />}
    </button>
  );
}

export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-white shadow-glow"
      style={{ width: size, height: size }}
    >
      <IconChart size={size * 0.55} />
    </span>
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

function Sidebar() {
  const { user, logout } = useAuth();
  const meta = useMetadata();
  const items = navItemsFor(user?.role);
  const sections = [...new Set(items.map((i) => i.section))];
  const coverage = meta.data?.coverage;
  return (
    <aside className="relative overflow-hidden bg-sidebar text-sidebar-ink lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
      <span
        className="pointer-events-none absolute -left-16 -top-24 h-64 w-64 rounded-full opacity-60 blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(37,99,235,0.45), transparent 70%)" }}
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute -bottom-24 -right-20 h-56 w-56 rounded-full opacity-40 blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(6,182,212,0.4), transparent 70%)" }}
        aria-hidden="true"
      />
      <div className="flex items-center gap-3 px-5 py-5">
        <BrandMark />
        <div className="leading-tight">
          <div className="text-[15px] font-bold tracking-tight text-white">Self-Service BI</div>
          <div className="text-xs text-sidebar-muted">Semantic layer · Olist Brazil</div>
        </div>
      </div>

      <nav
        className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-1 lg:flex-col lg:gap-0 lg:overflow-y-auto lg:pb-0"
        aria-label="Main"
      >
        {sections.map((section) => (
          <div key={section} className="flex gap-1 lg:mb-5 lg:block">
            <p className="hidden px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted lg:block">
              {section}
            </p>
            {items
              .filter((i) => i.section === section)
              .map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `group relative flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition lg:mb-0.5 ${
                      isActive
                        ? "bg-white/10 text-white"
                        : "text-sidebar-muted hover:bg-white/5 hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 top-2 hidden h-6 w-1 rounded-r-full bg-gradient-to-b from-accent to-accent-2 lg:block" />
                      )}
                      <Icon size={18} />
                      {label}
                    </>
                  )}
                </NavLink>
              ))}
          </div>
        ))}
      </nav>

      {coverage && (
        <div className="mx-4 mb-3 hidden rounded-xl border border-white/10 bg-white/5 p-3 text-xs lg:block">
          <p className="font-semibold text-white">Data available</p>
          <p className="mt-0.5 text-sidebar-muted">
            {coverage.min_date} → {coverage.max_date}
          </p>
          <p className="mt-0.5 text-sidebar-muted">Brazil · values in R$</p>
        </div>
      )}

      {user && (
        <div className="mx-3 mb-4 hidden items-center gap-3 rounded-xl bg-sidebar-2 p-3 lg:flex">
          <Avatar name={user.full_name || user.email} />
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-sm font-semibold text-white">
              {user.full_name || user.email}
            </div>
            <div className="truncate text-xs text-sidebar-muted">{user.email}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg p-1.5 text-sidebar-muted transition hover:bg-white/10 hover:text-white"
            aria-label="Sign out"
            title="Sign out"
          >
            <IconLogout size={18} />
          </button>
        </div>
      )}
    </aside>
  );
}

function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
      <Sidebar />
      <div className="min-w-0">
        <header
          className="sticky top-0 z-30 flex items-center gap-3 border-b border-line px-4 py-3 backdrop-blur-md sm:px-8"
          style={{ background: "color-mix(in srgb, var(--page) 78%, transparent)" }}
        >
          {location.pathname !== "/ask" ? (
            <Link
              to="/ask"
              className="group flex max-w-md flex-1 items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-2 text-sm text-muted shadow-sm transition hover:border-accent hover:text-ink-2"
            >
              <IconSearch size={16} />
              <span className="truncate">Ask a question about sales, orders, customers…</span>
            </Link>
          ) : (
            <div className="flex-1" />
          )}
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {user && (
              <div className="flex items-center gap-2.5 rounded-full border border-line bg-surface py-1 pl-1 pr-3 shadow-sm">
                <Avatar name={user.full_name || user.email} size={28} />
                <span className="hidden text-sm font-medium sm:inline">
                  {user.full_name || user.email}
                </span>
                <RoleBadge role={user.role} />
              </div>
            )}
            <button
              type="button"
              className="btn-ghost h-9 w-9 rounded-full p-0 lg:hidden"
              onClick={logout}
              aria-label="Sign out"
              title="Sign out"
            >
              <IconLogout size={18} />
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-8 sm:py-9">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
