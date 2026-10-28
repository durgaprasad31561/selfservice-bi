import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../api/client";
import { historyApi } from "../api/endpoints";
import { IconTrash } from "../components/Icons";
import { EmptyState, ErrorNote, PageHeader, Spinner, StatusBadge } from "../components/ui";
import { useHistory } from "../hooks/queries";
import { useAuth } from "../hooks/useAuth";
import { formatDateTime } from "../utils/format";

const PAGE = 25;
const FILTERS = [
  { value: "", label: "All" },
  { value: "answered", label: "Answered" },
  { value: "answered_with_warning", label: "With warning" },
  { value: "refused", label: "Refused" },
  { value: "clarify", label: "Clarification" },
  { value: "error", label: "Errors" },
];

export function HistoryPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [params] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [allUsers, setAllUsers] = useState(isAdmin && params.get("all") === "1");
  const showAll = isAdmin && allUsers;
  const history = useHistory({
    limit: PAGE,
    offset,
    status: status || undefined,
    all_users: showAll || undefined,
  });
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const remove = async (id: number) => {
    try {
      await historyApi.remove(id);
      await qc.invalidateQueries({ queryKey: ["history"] });
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const total = history.data?.total ?? 0;
  return (
    <div>
      <PageHeader
        title="History"
        subtitle={
          showAll
            ? "Every question asked by every user, and what happened to it."
            : "Every question you asked and what happened to it."
        }
        actions={
          isAdmin && (
            <div
              className="inline-flex rounded-lg border border-line p-0.5 text-sm"
              role="group"
              aria-label="Whose history"
            >
              {[
                { all: false, label: "Mine" },
                { all: true, label: "All users" },
              ].map((o) => (
                <button
                  key={o.label}
                  type="button"
                  aria-pressed={showAll === o.all}
                  onClick={() => {
                    setAllUsers(o.all);
                    setOffset(0);
                  }}
                  className={`btn px-3 py-1 ${showAll === o.all ? "bg-surface-2 text-ink" : "text-muted"}`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          )
        }
      />
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            aria-pressed={status === f.value}
            onClick={() => {
              setStatus(f.value);
              setOffset(0);
            }}
            className={`rounded-full border px-3 py-1 text-sm ${status === f.value ? "border-accent bg-accent-soft text-ink" : "border-line text-ink-2 hover:text-ink"}`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {error && (
        <div className="mb-3">
          <ErrorNote message={error} />
        </div>
      )}
      {history.isLoading && <Spinner />}
      {history.error && <ErrorNote message={errorMessage(history.error)} />}
      {history.data && history.data.items.length === 0 && (
        <EmptyState title="No questions yet">
          Go to the{" "}
          <Link to="/ask" className="text-accent hover:underline">
            Ask page
          </Link>{" "}
          to get started.
        </EmptyState>
      )}
      {history.data && history.data.items.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-ink-2">
              <tr>
                <th className="px-4 py-2 font-medium">Question</th>
                {showAll && <th className="px-4 py-2 font-medium">User</th>}
                <th className="px-4 py-2 font-medium">Outcome</th>
                <th className="px-4 py-2 text-right font-medium">Time</th>
                <th className="px-4 py-2 font-medium">Asked</th>
                <th className="px-4 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((h) => (
                <tr key={h.id} className="border-t border-line align-top">
                  <td className="max-w-md px-4 py-2.5">
                    <div className="font-medium">{h.question}</div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-ink-2">
                      {h.status === "refused" ? h.reason : h.answer_text}
                    </div>
                  </td>
                  {showAll && (
                    <td className="whitespace-nowrap px-4 py-2.5 text-ink-2">
                      {h.user_email ?? "—"}
                    </td>
                  )}
                  <td className="whitespace-nowrap px-4 py-2.5">
                    <StatusBadge status={h.status} />
                    {h.confidence && h.status.startsWith("answered") && (
                      <div className="mt-1 text-xs text-muted">{h.confidence} confidence</div>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink-2">
                    {(h.execution_ms / 1000).toFixed(1)} s
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-ink-2">
                    {formatDateTime(h.created_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-right">
                    <Link
                      to={`/ask?q=${encodeURIComponent(h.question)}`}
                      className="btn-ghost px-2 py-1 text-xs"
                    >
                      Ask again
                    </Link>
                    <button
                      type="button"
                      className="btn-ghost px-2 py-1"
                      aria-label="Delete entry"
                      onClick={() => void remove(h.id)}
                    >
                      <IconTrash size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-line px-4 py-2 text-sm text-ink-2">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-outline px-2.5 py-1"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn-outline px-2.5 py-1"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
