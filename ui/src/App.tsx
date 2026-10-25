import { AlertCircle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./screens/Dashboard";
import Connections from "./screens/Connections";
import Jobs from "./screens/Jobs";
import JobEditor from "./screens/JobEditor";
import RunHistory from "./screens/RunHistory";
import SettingsScreen from "./screens/SettingsScreen";
import RunModal from "./run/RunModal";
import { useStore } from "./store";

export default function App() {
  const { ready, screen, editingJob, editorOpen, runModal, toasts, dismissToast } = useStore();

  if (!ready) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 bg-bg text-muted">
        <Loader2 size={22} className="animate-spin text-accent" />
        <div className="text-sm">Confluence Export Desktop 준비 중…</div>
      </div>
    );
  }

  return (
    <div className="h-full flex bg-bg">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-7">
          {editorOpen && editingJob ? (
            <JobEditor job={editingJob} />
          ) : (
            <>
              {screen === "dashboard" && <Dashboard />}
              {screen === "connections" && <Connections />}
              {screen === "jobs" && <Jobs />}
              {screen === "history" && <RunHistory />}
              {screen === "settings" && <SettingsScreen />}
            </>
          )}
        </div>
      </main>

      {runModal && <RunModal jobId={runModal.jobId} />}

      <div className="fixed bottom-5 right-5 z-[60] space-y-2 w-80">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`card shadow-pop px-4 py-3 flex items-start gap-2.5 animate-fade-in text-sm ${
              toast.kind === "err"
                ? "border-err/40"
                : toast.kind === "ok"
                  ? "border-ok/40"
                  : "border-border"
            }`}
          >
            {toast.kind === "ok" ? (
              <CheckCircle2 size={15} className="text-ok mt-0.5 shrink-0" />
            ) : toast.kind === "err" ? (
              <AlertCircle size={15} className="text-err mt-0.5 shrink-0" />
            ) : (
              <Info size={15} className="text-accent mt-0.5 shrink-0" />
            )}
            <div className="flex-1 leading-relaxed">{toast.text}</div>
            <button type="button" className="text-faint hover:text-muted shrink-0" onClick={() => dismissToast(toast.id)}>
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
