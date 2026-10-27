import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardApi, historyApi, queryApi } from "../api/endpoints";
import type { PinRequest } from "../api/endpoints";

const STATIC = { staleTime: 10 * 60_000, refetchOnWindowFocus: false } as const;

export const useMetadata = () =>
  useQuery({ queryKey: ["metadata"], queryFn: queryApi.metadata, ...STATIC });

export const useSuggestions = () =>
  useQuery({ queryKey: ["suggestions"], queryFn: queryApi.suggestions, ...STATIC });

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: queryApi.overview, ...STATIC });

export const useDashboards = () =>
  useQuery({ queryKey: ["dashboards"], queryFn: dashboardApi.list });

export const useDashboard = (id: number) =>
  useQuery({ queryKey: ["dashboard", id], queryFn: () => dashboardApi.get(id), enabled: id > 0 });

export const useHistory = (params: { limit: number; offset: number; status?: string }) =>
  useQuery({ queryKey: ["history", params], queryFn: () => historyApi.list(params) });

export function useCreateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      dashboardApi.create(name, description),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboards"] }),
  });
}

export function usePinWidget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ dashboardId, body }: { dashboardId: number; body: PinRequest }) =>
      dashboardApi.addWidget(dashboardId, body),
    onSuccess: (_w, { dashboardId }) => {
      qc.invalidateQueries({ queryKey: ["dashboards"] });
      qc.invalidateQueries({ queryKey: ["dashboard", dashboardId] });
    },
  });
}

/** "YYYY-MM" months whose data is incomplete (from the semantic layer coverage table). */
export function useIncompleteMonths(): Set<string> {
  const meta = useMetadata();
  return useMemo(
    () =>
      new Set(
        (meta.data?.coverage?.months ?? []).filter((m) => m.status !== "full").map((m) => m.month),
      ),
    [meta.data],
  );
}
