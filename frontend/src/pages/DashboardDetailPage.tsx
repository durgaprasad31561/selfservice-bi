import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../api/client";
import { dashboardApi } from "../api/endpoints";
import { ChartView } from "../components/ChartView";
import { IconEdit, IconRefresh, IconTrash, IconWarning } from "../components/Icons";
import { EmptyState, ErrorNote, PageHeader, Spinner, StatusBadge } from "../components/ui";
import { useDashboard, useIncompleteMonths } from "../hooks/queries";
import type { Widget } from "../types/api";

function WidgetCard({
  widget,
  canEdit,
  onRename,
  onDelete,
}: {
  widget: Widget;
  canEdit: boolean;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(widget.title);
  const r = widget.result;
  const incompleteMonths = useIncompleteMonths();
  const type = widget.chart_type ?? r?.chart?.type ?? "table";
  return (
    <section className="card flex flex-col p-4">
      <div className="mb-3 flex items-start gap-2">
        {editing ? (
          <form
            className="flex flex-1 gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setEditing(false);
              if (title.trim()) onRename(title.trim());
            }}
          >
            <input
              className="input py-1"
              value={title}
              autoFocus
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
            />
            <button type="submit" className="btn-primary px-2.5 py-1">
              Save
            </button>
          </form>
        ) : (
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-semibold" title={widget.title}>
              {widget.title}
            </h2>
            {widget.question.trim() !== widget.title.trim() && (
              <p className="truncate text-xs text-muted" title={widget.question}>
                {widget.question}
              </p>
            )}
          </div>
        )}
        {canEdit && !editing && (
          <div className="flex shrink-0">
            <button
              type="button"
              className="btn-ghost px-1.5"
              aria-label="Rename widget"
              onClick={() => setEditing(true)}
            >
              <IconEdit size={16} />
            </button>
            <button
              type="button"
              className="btn-ghost px-1.5"
              aria-label="Remove widget"
              onClick={onDelete}
            >
              <IconTrash size={16} />
            </button>
          </div>
        )}
      </div>
      {!r ? (
        <Spinner />
      ) : r.status === "answered" || r.status === "answered_with_warning" ? (
        <>
          {type !== "kpi" && <p className="mb-2 text-sm text-ink-2">{r.answer_text}</p>}
          <ChartView
            type={type}
            columns={r.columns}
            rows={r.data}
            x={r.chart?.x}
            y={r.chart?.y}
            series={r.chart?.series}
            height={240}
            compact
            incompleteMonths={incompleteMonths}
          />
          {r.warnings.length > 0 && (
            <p className="mt-2 flex gap-1.5 text-xs text-warn-ink">
              <span className="shrink-0">
                <IconWarning size={14} />
              </span>
              {r.warnings[0]}
            </p>
          )}
        </>
      ) : (
        <div className="text-sm text-ink-2">
          <StatusBadge status={r.status} />
          <p className="mt-2">{r.reason ?? r.answer_text}</p>
        </div>
      )}
    </section>
  );
}

export function DashboardDetailPage() {
  const id = Number(useParams().id);
  const dashboard = useDashboard(id);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["dashboard", id] });
      await qc.invalidateQueries({ queryKey: ["dashboards"] });
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  if (dashboard.isLoading) return <Spinner label="Running widgets" />;
  if (dashboard.error || !dashboard.data) {
    return (
      <ErrorNote
        message={dashboard.error ? errorMessage(dashboard.error) : "Dashboard not found."}
      />
    );
  }
  const d = dashboard.data;
  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/dashboards" className="text-accent hover:underline">
          ← All dashboards
        </Link>
      </p>
      <PageHeader
        title={d.name}
        subtitle={
          d.description ||
          `${d.widgets.length} widget${d.widgets.length === 1 ? "" : "s"}, refreshed just now`
        }
        actions={
          <>
            <button
              type="button"
              className="btn-outline"
              disabled={dashboard.isFetching}
              onClick={() => qc.invalidateQueries({ queryKey: ["dashboard", id] })}
            >
              <IconRefresh size={16} /> {dashboard.isFetching ? "Refreshing…" : "Refresh"}
            </button>
            {d.can_edit && (
              <>
                <button
                  type="button"
                  className="btn-outline"
                  onClick={() => {
                    setName(d.name);
                    setRenaming(true);
                  }}
                >
                  <IconEdit size={16} /> Rename
                </button>
                <button
                  type="button"
                  className="btn-outline text-critical"
                  onClick={() => {
                    if (window.confirm(`Delete “${d.name}” and its widgets?`)) {
                      void act(() => dashboardApi.remove(id)).then(() => navigate("/dashboards"));
                    }
                  }}
                >
                  <IconTrash size={16} /> Delete
                </button>
              </>
            )}
          </>
        }
      />
      {renaming && (
        <form
          className="card mb-5 flex gap-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            setRenaming(false);
            if (name.trim()) void act(() => dashboardApi.update(id, { name: name.trim() }));
          }}
        >
          <input
            className="input"
            value={name}
            autoFocus
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
            aria-label="Dashboard name"
          />
          <button type="submit" className="btn-primary">
            Save
          </button>
          <button type="button" className="btn-ghost" onClick={() => setRenaming(false)}>
            Cancel
          </button>
        </form>
      )}
      {error && (
        <div className="mb-4">
          <ErrorNote message={error} />
        </div>
      )}
      {d.widgets.length === 0 ? (
        <EmptyState title="This dashboard is empty">
          Ask a question on the{" "}
          <Link to="/ask" className="text-accent hover:underline">
            Ask page
          </Link>{" "}
          and pin the answer here.
        </EmptyState>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {d.widgets.map((w) => (
            <WidgetCard
              key={w.id}
              widget={w}
              canEdit={d.can_edit}
              onRename={(title) => void act(() => dashboardApi.updateWidget(id, w.id, { title }))}
              onDelete={() => void act(() => dashboardApi.removeWidget(id, w.id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
