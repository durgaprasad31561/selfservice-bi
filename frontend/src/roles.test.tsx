/** Role-based UI: navigation, Admin page access, and analyst-only actions. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { navItemsFor } from "./components/Layout";
import { ResultCard } from "./components/ResultCard";
import { AdminPage } from "./pages/AdminPage";
import { makeResponse } from "./test/fixtures";
import type { Role, User } from "./types/api";

const auth = vi.hoisted(() => ({ role: "viewer" as string }));

vi.mock("./hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      email: "me@demo.com",
      full_name: "Me",
      role: auth.role,
      is_active: true,
      created_at: "2026-10-27T10:00:00Z",
    },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    canEditDashboards: auth.role === "admin" || auth.role === "analyst",
  }),
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}));

const updateUser = vi.fn(async (id: number, body: { role?: Role; is_active?: boolean }) => ({
  id,
  ...body,
}));
vi.mock("./api/endpoints", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/endpoints")>();
  const users: User[] = [
    {
      id: 1,
      email: "me@demo.com",
      full_name: "Me",
      role: "admin",
      is_active: true,
      created_at: "2026-10-27T10:00:00Z",
    },
    {
      id: 2,
      email: "ana@demo.com",
      full_name: "Ana",
      role: "analyst",
      is_active: true,
      created_at: "2026-10-27T10:00:00Z",
    },
    {
      id: 3,
      email: "vic@demo.com",
      full_name: "Vic",
      role: "viewer",
      is_active: false,
      created_at: "2026-10-27T10:00:00Z",
    },
  ];
  return {
    ...actual,
    queryApi: { ...actual.queryApi, metadata: async () => ({ coverage: null }) },
    dashboardApi: { ...actual.dashboardApi, list: async () => [] },
    adminApi: {
      users: async () => users,
      createUser: vi.fn(),
      updateUser: (id: number, body: object) => updateUser(id, body),
    },
  };
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("navigation by role", () => {
  it("shows Admin only to admins", () => {
    expect(navItemsFor("admin").map((n) => n.label)).toContain("Admin");
    expect(navItemsFor("analyst").map((n) => n.label)).not.toContain("Admin");
    expect(navItemsFor("viewer").map((n) => n.label)).not.toContain("Admin");
    expect(navItemsFor("viewer").map((n) => n.label)).toContain("Dashboards");
    expect(navItemsFor("analyst").map((n) => n.label)).toContain("My Dashboards");
  });
});

describe("Admin page", () => {
  it("is refused for non-admins", async () => {
    auth.role = "analyst";
    wrap(<AdminPage />);
    expect(screen.getByText("Admins only")).toBeInTheDocument();
  });

  it("lists users, blocks editing yourself and changes another user's role", async () => {
    auth.role = "admin";
    wrap(<AdminPage />);
    expect(await screen.findByText("ana@demo.com")).toBeInTheDocument();
    expect(screen.getByText("Deactivated")).toBeInTheDocument();
    expect(screen.getByLabelText("Role for me@demo.com")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Role for ana@demo.com"), {
      target: { value: "viewer" },
    });
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith(2, { role: "viewer" }));
    fireEvent.click(screen.getByRole("button", { name: "Reactivate" }));
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith(3, { is_active: true }));
  });
});

describe("analyst-only actions", () => {
  it("hides Pin for viewers and shows it for analysts", async () => {
    auth.role = "viewer";
    const { unmount } = wrap(<ResultCard response={makeResponse()} />);
    expect(screen.queryByRole("button", { name: /Pin to dashboard/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export CSV/ })).toBeInTheDocument();
    unmount();
    auth.role = "analyst";
    wrap(<ResultCard response={makeResponse()} />);
    expect(screen.getByRole("button", { name: /Pin to dashboard/ })).toBeInTheDocument();
  });
});
