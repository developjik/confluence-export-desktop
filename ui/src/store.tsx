import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, isTauri } from "./ipc";
import type { Job, RunRecord, StateSnapshot } from "./types";

export type Screen = "dashboard" | "connections" | "jobs" | "history" | "settings";

export interface Toast {
  id: number;
  kind: "ok" | "err" | "info";
  text: string;
}

interface RunModalState {
  jobId: string;
}

interface StoreValue {
  ready: boolean;
  snapshot: StateSnapshot | null;
  screen: Screen;
  navigate: (screen: Screen) => void;
  editingJob: Job | null;
  editorOpen: boolean;
  openEditor: (job: Job | null) => void;
  closeEditor: () => void;
  runModal: RunModalState | null;
  openRunModal: (jobId: string) => void;
  closeRunModal: () => void;
  nextRuns: Record<string, string | null>;
  refresh: () => Promise<void>;
  toasts: Toast[];
  pushToast: (kind: Toast["kind"], text: string) => void;
  dismissToast: (id: number) => void;
}

const StoreContext = createContext<StoreValue | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [snapshot, setSnapshot] = useState<StateSnapshot | null>(null);
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [editingJob, setEditingJob] = useState<Job | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [runModal, setRunModal] = useState<RunModalState | null>(null);
  const [nextRuns, setNextRuns] = useState<Record<string, string | null>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastSeq = useRef(1);

  const pushToast = useCallback((kind: Toast["kind"], text: string) => {
    const id = toastSeq.current++;
    setToasts((prev) => [...prev, { id, kind, text }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, kind === "err" ? 6000 : 3500);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getState();
      setSnapshot(next);
    } catch (err) {
      console.error("state refresh failed", err);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setReady(true);
    })();
  }, [refresh]);

  // keep next-run times fresh for the jobs screen
  useEffect(() => {
    if (!isTauri) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await api.getNextRuns();
        if (!cancelled) setNextRuns(next);
      } catch {
        /* scheduler info is non-critical */
      }
    };
    poll();
    const timer = window.setInterval(poll, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [snapshot?.jobs.length, editorOpen]);

  // react to background run completions
  useEffect(() => {
    if (!isTauri) return;
    let unlisten: (() => void) | null = null;
    (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      const stop = await listen("runs://changed", () => {
        refresh();
      });
      unlisten = stop;
    })();
    return () => unlisten?.();
  }, [refresh]);

  // persist + apply theme
  useEffect(() => {
    const theme = snapshot?.settings.theme ?? "system";
    try {
      localStorage.setItem("ced-theme", JSON.stringify(theme));
    } catch {
      /* ignore */
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme !== "light" && media.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [snapshot?.settings.theme]);

  const value = useMemo<StoreValue>(
    () => ({
      ready,
      snapshot,
      screen,
      navigate: setScreen,
      editingJob,
      editorOpen,
      openEditor: (job: Job | null) => {
        setEditingJob(job);
        setEditorOpen(true);
      },
      closeEditor: () => setEditorOpen(false),
      runModal,
      openRunModal: (jobId: string) => setRunModal({ jobId }),
      closeRunModal: () => setRunModal(null),
      nextRuns,
      refresh,
      toasts,
      pushToast,
      dismissToast,
    }),
    [ready, snapshot, screen, editingJob, editorOpen, runModal, nextRuns, refresh, toasts, pushToast, dismissToast],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside AppProvider");
  return ctx;
}

export function lastRunForJob(runs: RunRecord[] | undefined, jobId: string): RunRecord | undefined {
  return runs?.filter((r) => r.job_id === jobId)[0];
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return "-";
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (Number.isNaN(ms) || ms < 0) return "-";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}초`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}분 ${seconds % 60}초`;
}
