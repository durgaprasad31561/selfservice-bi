import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorMessage } from "../api/client";
import { adminApi } from "../api/endpoints";
import { IconPlus } from "../components/Icons";
import { EmptyState, ErrorNote, PageHeader, RoleBadge, Spinner } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import type { Role, User } from "../types/api";
import { formatDateTime } from "../utils/format";

const ROLES: { value: Role; label: string; can: string }[] = [
  { value: "viewer", label: "Viewer", can: "Ask questions and view dashboards" },
  { value: "analyst", label: "Analyst", can: "Also create and edit their own dashboards" },
  { value: "admin", label: "Admin", can: "Everything, including managing users" },
];

function CreateUser({ onCreated }: { onCreated: (email: string) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const create = useMutation({
    mutationFn: () => adminApi.createUser({ email, password, full_name: fullName, role }),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setEmail("");
      setFullName("");
      setPassword("");
      setRole("viewer");
      onCreated(u.email);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  return (
    <form onSubmit={submit} className="card grid gap-3 p-4 md:grid-cols-[1fr_1fr_1fr_auto_auto]">
      <div>
        <label className="label" htmlFor="new-email">
          Email
        </label>
        <input
          id="new-email"
          type="email"
          className="input"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div>
        <label className="label" htmlFor="new-name">
          Full name
        </label>
        <input
          id="new-name"
          className="input"
          maxLength={120}
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
      </div>
      <div>
        <label className="label" htmlFor="new-password">
          Password (min. 8)
        </label>
        <input
          id="new-password"
          type="password"
          className="input"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <div>
        <label className="label" htmlFor="new-role">
          Role
        </label>
        <select
          id="new-role"
          className="input"
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-end">
        <button type="submit" className="btn-primary w-full" disabled={create.isPending}>
          <IconPlus size={16} /> {create.isPending ? "Creating…" : "Create user"}
        </button>
      </div>
      {create.error && (
        <p className="text-sm text-critical md:col-span-5" role="alert">
          {errorMessage(create.error)}
        </p>
      )}
    </form>
  );
}

function UserRow({ user, isSelf }: { user: User; isSelf: boolean }) {
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: (body: { role?: Role; is_active?: boolean }) => adminApi.updateUser(user.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
  return (
    <tr className={`border-t border-line ${user.is_active ? "" : "text-muted"}`}>
      <td className="px-4 py-2.5">
        <div className="font-medium">
          {user.full_name || "—"}
          {isSelf && <span className="ml-2 text-xs text-muted">(you)</span>}
        </div>
        <div className="text-xs text-ink-2">{user.email}</div>
      </td>
      <td className="px-4 py-2.5">
        <label className="sr-only" htmlFor={`role-${user.id}`}>
          Role for {user.email}
        </label>
        <select
          id={`role-${user.id}`}
          className="input w-36 py-1"
          value={user.role}
          disabled={isSelf || update.isPending}
          title={isSelf ? "You cannot change your own role" : undefined}
          onChange={(e) => update.mutate({ role: e.target.value as Role })}
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </td>
      <td className="whitespace-nowrap px-4 py-2.5">
        <span
          className={`inline-flex items-center gap-1.5 text-sm ${user.is_active ? "text-good" : "text-muted"}`}
        >
          <span
            className={`h-2 w-2 rounded-full ${user.is_active ? "bg-good" : "bg-grid"}`}
            aria-hidden="true"
          />
          {user.is_active ? "Active" : "Deactivated"}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-ink-2">
        {formatDateTime(user.created_at)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-right">
        {!isSelf && (
          <button
            type="button"
            className="btn-outline px-2.5 py-1 text-xs"
            disabled={update.isPending}
            onClick={() => update.mutate({ is_active: !user.is_active })}
          >
            {user.is_active ? "Deactivate" : "Reactivate"}
          </button>
        )}
        {update.error && (
          <div className="mt-1 text-xs text-critical">{errorMessage(update.error)}</div>
        )}
      </td>
    </tr>
  );
}

export function AdminPage() {
  const { user } = useAuth();
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.users,
    enabled: user?.role === "admin",
  });
  const [created, setCreated] = useState<string | null>(null);

  if (user?.role !== "admin") {
    return (
      <EmptyState title="Admins only">
        This page manages users and roles.{" "}
        <Link to="/" className="text-accent hover:underline">
          Back to the overview
        </Link>
      </EmptyState>
    );
  }

  const list = users.data ?? [];
  const counts = ROLES.map((r) => ({
    ...r,
    n: list.filter((u) => u.role === r.value && u.is_active).length,
  }));
  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin"
        subtitle="Manage who can use the system and what they can do. Changes apply on the user's next request."
        actions={
          <Link to="/history?all=1" className="btn-outline">
            All users' history
          </Link>
        }
      />

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Roles">
        {counts.map((r) => (
          <div key={r.value} className="card p-4">
            <div className="flex items-center justify-between">
              <RoleBadge role={r.value} />
              <span className="text-2xl font-semibold tabular-nums">{r.n}</span>
            </div>
            <p className="mt-2 text-sm text-ink-2">{r.can}</p>
          </div>
        ))}
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Add a user</h2>
        <CreateUser onCreated={setCreated} />
        {created && (
          <p className="mt-2 text-sm text-good" role="status">
            Created {created}.
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">
          Users <span className="text-sm font-normal text-muted">({list.length})</span>
        </h2>
        {users.isLoading && <Spinner />}
        {users.error && <ErrorNote message={errorMessage(users.error)} />}
        {list.length > 0 && (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-ink-2">
                <tr>
                  <th className="px-4 py-2 font-medium">User</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                  <th className="px-4 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((u) => (
                  <UserRow key={u.id} user={u} isSelf={u.id === user.id} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
