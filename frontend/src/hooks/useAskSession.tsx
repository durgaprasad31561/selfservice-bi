import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { errorMessage } from "../api/client";
import { queryApi } from "../api/endpoints";
import type { QueryResponse } from "../types/api";

export interface AskEntry {
  id: string;
  question: string;
  pending: boolean;
  response?: QueryResponse;
  error?: string;
}

interface AskSession {
  entries: AskEntry[];
  busy: boolean;
  ask: (question: string) => Promise<void>;
  clear: () => void;
}

const Ctx = createContext<AskSession | null>(null);

/** Keeps the Ask page conversation while the user navigates between pages. */
export function AskSessionProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<AskEntry[]>([]);
  const busy = entries.some((e) => e.pending);

  const ask = useCallback(async (question: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setEntries((prev) => [{ id, question, pending: true }, ...prev].slice(0, 20));
    try {
      const response = await queryApi.ask(question);
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, pending: false, response } : e)));
    } catch (err) {
      const error = errorMessage(err);
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, pending: false, error } : e)));
    }
  }, []);

  const clear = useCallback(() => setEntries([]), []);
  return <Ctx.Provider value={{ entries, busy, ask, clear }}>{children}</Ctx.Provider>;
}

export function useAskSession(): AskSession {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAskSession must be used inside <AskSessionProvider>");
  return ctx;
}
