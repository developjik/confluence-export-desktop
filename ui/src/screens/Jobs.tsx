import { useState } from "react";
import {
  CalendarClock,
  Copy,
  FolderOpen,
  FolderSync,
  Loader2,
  Pencil,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { api, toAppError } from "../ipc";
import { formatDateTime, useStore } from "../store";
import { EmptyState, Modal, StatusChip } from "../components/ui";
import { SCOPE_LABELS, type Job } from "../types";

export default function Jobs() {
  const { snapshot, openEditor, openRunModal, refresh, pushToast, nextRuns } = useStore();
  const jobs = snapshot?.jobs ?? [];
  const runs = snapshot?.runs ?? [];
  const [confirmDelete, setConfirmDelete] = useState<Job | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const runningJob = runs.find((r) => r.status === "running")?.job_id;

  const createNew = () =>
    openEditor({
      id: "",
      name: "",
      confluence_url: snapshot?.settings.base_url ? `${snapshot.settings.base_url}/wiki/spaces/` : "",
      target_dir: "",
      include_children: true,
      include_attachments: true,
      enabled: true,
      export_options: {
        scope: "auto",
        urls: "",
        config_json: "",
        page_link: "relative",
        attachment_link: "relative",
        attachment_export_all: true,
        page_breadcrumbs: true,
        page_properties_as_front_matter: true,
        front_matter_standard: true,
        include_document_title: false,
        skip_unchanged: true,
        cleanup_stale: true,
        timeout_seconds: 30,
        max_requests: 8,
        verify_ssl: true,
        page_path: "{space_name}/{homepage_title}/{ancestor_titles}/{page_title}.md",
        attachment_path: "{space_name}/attachments/{attachment_file_id}{attachment_extension}",
        filename_max_length: 120,
      },
      schedule: {
        enabled: false,
        kind: "daily",
        times: ["09:00"],
        days_of_week: [1, 2, 3, 4, 5],
        day_of_month: null,
        timezone: "Asia/Seoul",
        paused: false,
      },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

  const handleDuplicate = async (job: Job) => {
    setBusyId(job.id);
    try {
      await api.duplicateJob(job.id);
      await refresh();
      pushToast("ok", "작업을 복제했습니다.");
    } catch (err) {
      pushToast("err", toAppError(err).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setBusyId(confirmDelete.id);
    try {
      await api.deleteJob(confirmDelete.id);
      await refresh();
      pushToast("ok", "작업을 삭제했습니다.");
      setConfirmDelete(null);
    } catch (err) {
      pushToast("err", toAppError(err).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleOpenFolder = async (job: Job) => {
    try {
      await api.openFolder(job.target_dir);
    } catch (err) {
      pushToast("err", toAppError(err).message);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">작업</h1>
          <p className="text-sm text-muted mt-1">저장된 내보내기 작업을 관리하고 즉시 실행하세요.</p>
        </div>
        <button type="button" className="btn-primary" onClick={createNew}>
          <Plus size={15} /> 새 작업
        </button>
      </header>

      {jobs.length === 0 ? (
        <EmptyState
          icon={<FolderSync size={20} />}
          title="아직 작업이 없습니다"
          description="새 작업을 만들어 Confluence 스페이스나 페이지를 Markdown으로 내보내세요. 예약을 켜면 매일 자동 실행됩니다."
          action={
            <button type="button" className="btn-primary mt-1" onClick={createNew}>
              <Plus size={15} /> 작업 만들기
            </button>
          }
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {jobs.map((job) => {
            const lastRun = runs.find((r) => r.job_id === job.id);
            const next = nextRuns[job.id];
            const scopeLabel = SCOPE_LABELS[job.export_options.scope === "auto" ? "auto" : job.export_options.scope];
            const isRunning = runningJob === job.id;
            return (
              <article key={job.id} className="card px-5 py-4 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="text-[15px] font-semibold truncate flex items-center gap-2">
                      {job.name}
                      {!job.enabled && <span className="text-[10px] text-faint font-medium">(사용 안 함)</span>}
                    </h3>
                    <div className="text-xs text-muted mt-1 truncate" title={job.export_options.urls || job.confluence_url}>
                      {job.export_options.urls || job.confluence_url}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[11px] font-semibold text-accent">
                    {scopeLabel}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
                  <span className="inline-flex items-center gap-1" title={job.target_dir}>
                    <FolderOpen size={12} /> <span className="truncate max-w-[220px]">{job.target_dir}</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <CalendarClock size={12} />
                    {job.schedule.enabled && !job.schedule.paused
                      ? next
                        ? `다음 실행 ${formatDateTime(next)}`
                        : scheduleSummary(job)
                      : "예약 꺼짐"}
                  </span>
                  {lastRun && (
                    <span className="inline-flex items-center gap-1.5">
                      <StatusChip status={lastRun.status} />
                      <span>{formatDateTime(lastRun.started_at)}</span>
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1.5 pt-1 border-t border-border/70">
                  <button
                    type="button"
                    className="btn-primary !h-8 !text-[13px]"
                    disabled={isRunning}
                    onClick={() => openRunModal(job.id)}
                  >
                    {isRunning ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                    {isRunning ? "실행 중…" : "지금 내보내기"}
                  </button>
                  <button type="button" className="btn-secondary !h-8 !text-[13px]" onClick={() => openEditor(job)}>
                    <Pencil size={13} /> 편집
                  </button>
                  <button type="button" className="btn-ghost !h-8 !text-[13px]" onClick={() => handleOpenFolder(job)}>
                    <FolderOpen size={13} /> 폴더
                  </button>
                  <div className="ml-auto flex items-center gap-1">
                    <button
                      type="button"
                      className="btn-ghost !h-8 !px-2"
                      title="복제"
                      disabled={busyId === job.id}
                      onClick={() => handleDuplicate(job)}
                    >
                      {busyId === job.id ? <Loader2 size={13} className="animate-spin" /> : <Copy size={13} />}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost !h-8 !px-2 text-err hover:text-err"
                      title="삭제"
                      onClick={() => setConfirmDelete(job)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <Modal open={confirmDelete !== null} onClose={() => setConfirmDelete(null)} title="작업 삭제">
        <p className="text-sm text-muted leading-relaxed">
          <span className="font-semibold text-text">{confirmDelete?.name}</span> 작업을 삭제할까요? 이미 내보낸 파일은
          그대로 남습니다.
        </p>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(null)}>
            취소
          </button>
          <button type="button" className="btn-danger" onClick={handleDelete} disabled={busyId === confirmDelete?.id}>
            {busyId === confirmDelete?.id && <Loader2 size={14} className="animate-spin" />}
            삭제
          </button>
        </div>
      </Modal>
    </div>
  );
}

function scheduleSummary(job: Job): string {
  const times = job.schedule.times.join(", ");
  switch (job.schedule.kind) {
    case "daily":
      return `매일 ${times}`;
    case "weekly": {
      const days = job.schedule.days_of_week
        .slice()
        .sort()
        .map((d) => ["월", "화", "수", "목", "금", "토", "일"][d - 1] ?? "")
        .join("");
      return `매주 ${days}요일 ${times}`;
    }
    case "monthly":
      return `매월 ${job.schedule.day_of_month ?? 1}일 ${times}`;
  }
}
