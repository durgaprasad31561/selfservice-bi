import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { IconGrid, IconPlus } from "../components/Icons";
import { EmptyState, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useCreateDashboard, useDashboards } from "../hooks/queries";
import { useAuth } from "../hooks/useAuth";
import { formatDateTime } from "../utils/format";

export function DashboardsPage() {
  const { canEditDashboards, user } = useAuth();
  const dashboards = useDashboards();
  const create = useCreateDashboard();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      const d = await create.mutateAsync({ name: name.trim() });
      setName("");
      navigate(`/dashboards/${d.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const mine = (dashboards.data ?? []).filter((d) => d.owner_id === user?.id);
  const others = (dashboards.data ?? []).filter((d) => d.owner_id !== user?.id);

  return (
    <div>
      <PageHeader
        title="My Dashboards"
        subtitle="Pin answers from the Ask page. Widgets re-run every time a dashboard opens, so figures are always current."
      />
      {canEditDashboards && (
        <form onSubmit={submit} className="card mb-6 flex flex-wrap items-end gap-3 p-4">
          <div className="min-w-[16rem] flex-1">
            <label className="label" htmlFor="dash-name">New dashboard</label>
            <input id="dash-name" className="input" placeholder="e.g. Sales review 2018" value={name}
                   maxLength={120} onChange={(e) => setName(e.target.value)} />
          </div>
          <button type="submit" className="btn-primary" disabled={!name.trim() || create.isPending}>
            <IconPlus size={16} /> Create
          </button>
          {error && <p className="w-full text-sm text-critical">{error}</p>}
        </form>
      )}
      {dashboards.isLoading && <Spinner />}
      {dashboards.error && <ErrorNote message={errorMessage(dashboards.error)} />}
      {dashboards.data && dashboards.data.length === 0 && (
        <EmptyState title="No dashboards yet">
          {canEditDashboards
            ? "Create one above, or ask a question and choose “Pin to dashboard”."
            : "Analysts create dashboards; they will appear here for you to view."}
        </EmptyState>
      )}
      {[{ title: "Yours", list: mine }, { title: "Shared by others", list: others }].map(
        ({ title, list }) =>
          list.length > 0 && (
            <section key={title} className="mb-6">
              <h2 className="label">{title}</h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {list.map((d) => (
                  <Link key={d.id} to={`/dashboards/${d.id}`} className="card block p-4 hover:border-accent">
                    <div className="flex items-center gap-2">
                      <span className="text-accent"><IconGrid size={18} /></span>
                      <h3 className="truncate font-semibold">{d.name}</h3>
                    </div>
                    {d.description && <p className="mt-1 line-clamp-2 text-sm text-ink-2">{d.description}</p>}
                    <p className="mt-3 text-xs text-muted">
                      {d.widget_count} widget{d.widget_count === 1 ? "" : "s"} · updated {formatDateTime(d.updated_at)}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          ),
      )}
    </div>
  );
}
