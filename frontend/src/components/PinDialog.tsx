import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../api/client";
import { useCreateDashboard, useDashboards, usePinWidget } from "../hooks/queries";
import type { QueryResponse } from "../types/api";

interface Props {
  response: QueryResponse;
  onClose: () => void;
  onPinned: (dashboardName: string) => void;
}

export function PinDialog({ response, onClose, onPinned }: Props) {
  const dashboards = useDashboards();
  const create = useCreateDashboard();
  const pin = usePinWidget();
  const editable = (dashboards.data ?? []).filter((d) => d.can_edit);
  const [target, setTarget] = useState<string>("new");
  const [newName, setNewName] = useState("My dashboard");
  const [title, setTitle] = useState(response.chart?.title || response.question);
  const [error, setError] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    dialog.current?.showModal?.();
  }, []);
  useEffect(() => {
    if (editable.length && target === "new") setTarget(String(editable[0].id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable.length]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      let id = Number(target);
      let name = editable.find((d) => d.id === id)?.name ?? "";
      if (target === "new") {
        const d = await create.mutateAsync({ name: newName.trim() || "My dashboard" });
        id = d.id;
        name = d.name;
      }
      const custom = response.explanation.mode === "custom_sql";
      await pin.mutateAsync({
        dashboardId: id,
        body: {
          title: title.trim() || response.question,
          question: response.question,
          mode: custom ? "custom_sql" : "semantic",
          plan: custom ? null : response.plan,
          custom_sql: custom ? response.sql : null,
          chart_type: response.chart?.type ?? null,
        },
      });
      onPinned(name);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const busy = create.isPending || pin.isPending;
  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      onCancel={onClose}
      className="w-[min(92vw,440px)] rounded-xl border border-line bg-surface p-0 text-ink backdrop:bg-black/40"
    >
      <form onSubmit={submit} className="space-y-4 p-5">
        <h2 className="text-lg font-semibold">Pin to dashboard</h2>
        <p className="text-sm text-ink-2">
          The question and its definition are saved, not the numbers — the widget re-runs each time
          the dashboard opens.
        </p>
        <div>
          <label className="label" htmlFor="pin-title">Widget title</label>
          <input id="pin-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </div>
        <div>
          <label className="label" htmlFor="pin-target">Dashboard</label>
          <select id="pin-target" className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
            {editable.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
            <option value="new">+ New dashboard…</option>
          </select>
        </div>
        {target === "new" && (
          <div>
            <label className="label" htmlFor="pin-new">New dashboard name</label>
            <input id="pin-new" className="input" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={120} />
          </div>
        )}
        {error && <p className="text-sm text-critical" role="alert">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Pinning…" : "Pin"}</button>
        </div>
      </form>
    </dialog>
  );
}
