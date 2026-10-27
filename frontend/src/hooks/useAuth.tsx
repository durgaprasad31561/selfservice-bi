import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getToken, setToken, setUnauthorizedHandler } from "../api/client";
import { authApi } from "../api/endpoints";
import type { User } from "../types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  canEditDashboards: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => Boolean(getToken()));

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      queryClient.clear();
    });
    if (!getToken()) return;
    authApi
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, [queryClient]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      canEditDashboards: user?.role === "admin" || user?.role === "analyst",
    }),
    [user, loading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
