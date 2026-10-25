import { useEffect, useMemo, useRef, useState } from "react";
import { Ban, CheckCircle2, FolderOpen, Loader2, XCircle } from "lucide-react";
import { api, invoke, isTauri, setMockRunListener, toAppError } from "../ipc";
import { formatDuration, useStore } from "../store";
import { StatusChip } from "../components/ui";
import type { ProgressEvent, RunRecord, RunStats } from "../types";

const PHASES: { key: string; label: string }[] = [
  { key: "discover", label: "페이지 수집" },
  { key: "attachments", label: "첨부파일 확인" },
  { key: "convert", label: "변환 및 저장" },
  { key: "cleanup", label: "정리" },
  { key: "done", label: "완료" },
];

const EMPTY_STATS: RunStats = {
  pages_total: 0,
  pages_exported: 0,
  pages_skipped: 0,
  pages_failed: 0,
  attachments_total: 0,
  attachments_exported: 0,
  attachments_skipped: 0,
  files_removed: 0,
};

export default function RunModal({ jobId }: { jobId: string }) {
  const { closeRunModal, snapshot, refresh, pushToast } = useStore();
  const job = snapshot?.jobs.find((j) => j.id === jobId);
  const [phase, setPhase] = useState<string>("discover");
  const [stats, setStats] = useState<RunStats>(EMPTY_STATS);
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState<number | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<RunRecord | null>(null);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  // The run effect must fire exactly once per mount.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    let cancelled = false;
    const appendLog = (line: string) => {
      setLog((prev) => [...prev.slice(-400), line]);
    };

    const applyEvent = (event: ProgressEvent) => {
      if (cancelled) return;
      switch (event.type) {
        case "phase":
          setPhase(event.phase);
          appendLog(`— ${phaseLabel(event.phase)}`);
          break;
        case "message":
          appendLog(event.text);
          break;
        case "total":
          setTotal(event.total);
          break;
        case "pageStart":
          appendLog(`변환 중: ${event.title}`);
          break;
        case "pageDone": {
          if (event.outcome === "exported") {
            appendLog(`✓ ${event.title} → ${event.path ?? ""}`);
          } else if (event.outcome === "skipped") {
            appendLog(`· ${event.title} (변경 없음)`);
          } else {
            appendLog(`✗ ${event.title} 실패`);
          }
          setDone((prev) => prev + 1);
          break;
        }
        case "stats":
          setStats(event.stats);
          break;
      }
    };

    (async () => {
      try {
        let onProgress: unknown = undefined;
        if (isTauri) {
          const { Channel } = await import("@tauri-apps/api/core");
          const channel = new Channel<ProgressEvent>();
          channel.onmessage = applyEvent;
          onProgress = channel;
        } else {
          setMockRunListener(applyEvent);
        }
        const run = await invoke<RunRecord>("run_job", { jobId, onProgress });
        if (!cancelled) setResult(run);
      } catch (err) {
        const appErr = toAppError(err);
        if (!cancelled) setError(`${appErr.message}${appErr.detail ? ` — ${appErr.detail}` : ""}`);
      } finally {
        setMockRunListener(null);
        refresh();
      }
    })();

    return () => {
      cancelled = true;
      setMockRunListener(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await api.cancelRun(jobId);
    } catch {
      pushToast("err", "취소 요청이 실패했습니다.");
    }
  };

  const handleOpenFolder = async () => {
    if (job) await api.openFolder(job.target_dir);
  };

  const phaseIndex = PHASES.findIndex((p) => p.key === phase);
  const progress = total && total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  const finished = result !== null || error !== "";
  const status = result?.status ?? null;

  const counters = useMemo(
    () => [
      { label: "전체", value: stats.pages_total },
      { label: "내보냄", value: stats.pages_exported, cls: "text-ok" },
      { label: "건너뜀", value: stats.pages_skipped, cls: "text-muted" },
      { label: "실패", value: stats.pages_failed, cls: stats.pages_failed > 0 ? "text-err" : "" },
      { label: "첨부", value: `${stats.attachments_exported}/${stats.attachments_total}` },
      { label: "정리", value: stats.files_removed },
    ],
    [stats],
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" />
      <div className="relative card shadow-pop animate-fade-in w-full max-w-2xl max-h-[86vh] flex flex-col">
        <div className="flex items-start justify-between px-6 pt-5 pb-3">
          <div>
            <h2 className="text-base font-semibold flex items-center gap-2">
              {finished ? (
                status === "succeeded" ? (
                  <CheckCircle2 size={17} className="text-ok" />
                ) : (
                  <XCircle size={17} className={status === "cancelled" ? "text-muted" : "text-err"} />
                )
              ) : (
                <Loader2 size={16} className="animate-spin text-accent" />
              )}
              {job?.name ?? "작업"} 내보내기
            </h2>
            {finished && result ? (
              <div className="flex items-center gap-2 mt-1.5 text-xs text-muted">
                <StatusChip status={result.status} />
                <span>{formatDuration(result.started_at, result.finished_at)}</span>
              </div>
            ) : (
              <div className="text-xs text-muted mt-1">{phaseLabel(phase)}…</div>
            )}
          </div>
          {finished ? (
            <div className="flex items-center gap-2">
              <button type="button" className="btn-secondary !h-8" onClick={handleOpenFolder}>
                <FolderOpen size={13} /> 폴더 열기
              </button>
              <button type="button" className="btn-primary !h-8" onClick={closeRunModal}>
                닫기
              </button>
            </div>
          ) : (
            <button type="button" className="btn-danger !h-8" onClick={handleCancel} disabled={cancelling}>
              {cancelling ? <Loader2 size={13} className="animate-spin" /> : <Ban size={13} />}
              취소
            </button>
          )}
        </div>

        <div className="px-6 pb-6 overflow-y-auto space-y-4">
          {error && (
            <div className="rounded-lg border border-err/40 bg-err/10 px-4 py-3 text-sm text-err">{error}</div>
          )}

          {/* phase steps */}
          <div className="flex items-center gap-1">
            {PHASES.map((p, idx) => {
              const state = finished || idx < phaseIndex ? "done" : idx === phaseIndex ? "active" : "todo";
              return (
                <div key={p.key} className="flex items-center gap-1 flex-1 last:flex-none">
                  <div
                    className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold whitespace-nowrap ${
                      state === "done"
                        ? "bg-ok/10 text-ok"
                        : state === "active"
                          ? "bg-accent/10 text-accent"
                          : "text-faint"
                    }`}
                  >
                    {state === "done" ? <CheckCircle2 size={11} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                    {p.label}
                  </div>
                  {idx < PHASES.length - 1 && <div className="h-px flex-1 bg-border" />}
                </div>
              );
            })}
          </div>

          {/* progress bar */}
          <div>
            <div className="flex items-center justify-between text-xs text-muted mb-1.5">
              <span>
                페이지 {done}
                {total !== null ? ` / ${total}` : ""}
              </span>
              {progress !== null && <span className="tabular-nums">{progress}%</span>}
            </div>
            <div className="h-2 rounded-full bg-raised overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${status === "failed" ? "bg-err" : "bg-accent"}`}
                style={{ width: progress === null ? (finished ? "100%" : "12%") : `${progress}%` }}
              />
            </div>
          </div>

          {/* counters */}
          <div className="grid grid-cols-6 gap-2">
            {counters.map((counter) => (
              <div key={counter.label} className="rounded-xl bg-raised/60 border border-border px-2 py-2 text-center">
                <div className={`text-lg font-bold tabular-nums leading-tight ${counter.cls ?? ""}`}>{counter.value}</div>
                <div className="text-[10.5px] text-faint font-medium">{counter.label}</div>
              </div>
            ))}
          </div>

          {/* live log */}
          <div
            ref={logRef}
            className="h-44 overflow-y-auto rounded-xl bg-raised/60 border border-border px-3.5 py-2.5 font-mono text-[11.5px] leading-relaxed text-muted"
          >
            {log.length === 0 ? (
              <div className="text-faint">준비 중…</div>
            ) : (
              log.map((line, idx) => (
                <div key={idx} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))
            )}
            {result?.error && <div className="text-err mt-1 whitespace-pre-wrap">{result.error}</div>}
          </div>

          <div className="text-[11px] text-faint">
            {result
              ? `소요 ${formatDuration(result.started_at, result.finished_at)} · lockfile 기준으로 변경된 페이지만 다시 씁니다.`
              : "lockfile 기준으로 변경된 페이지만 다시 씁니다."}
          </div>
        </div>
      </div>
    </div>
  );
}

function phaseLabel(phase: string): string {
  return PHASES.find((p) => p.key === phase)?.label ?? phase;
}
