import { CheckCircle2, FileStack, Percent, Play, Plus, Timer } from "lucide-react";
import { formatDateTime, formatDuration, useStore } from "../store";
import { EmptyState, StatCard, StatusChip } from "../components/ui";
import { newJob } from "../types";

export default function Dashboard() {
  const { snapshot, openEditor, openRunModal, navigate } = useStore();
  const jobs = snapshot?.jobs ?? [];
  const runs = snapshot?.runs ?? [];
  const today = new Date().toDateString();
  const runsToday = runs.filter((r) => new Date(r.started_at).toDateString() === today);
  const recentFinished = runs.filter((r) => r.status !== "running").slice(0, 30);
  const successRate =
    recentFinished.length === 0
      ? null
      : Math.round((recentFinished.filter((r) => r.status === "succeeded").length / recentFinished.length) * 100);
  const activeScheduled = jobs.filter((j) => j.enabled && j.schedule.enabled && !j.schedule.paused).length;
  const connected = Boolean(snapshot?.has_token && snapshot?.settings.base_url);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">대시보드</h1>
          <p className="text-sm text-muted mt-1">Confluence 내보내기 현황을 한눈에 확인하세요.</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => openEditor(newJob(snapshot?.settings.base_url ?? ""))}>
          <Plus size={15} /> 새 작업 만들기
        </button>
      </header>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard label="전체 작업" value={jobs.length} sub={`활성 ${jobs.filter((j) => j.enabled).length}개`} icon={<FileStack size={18} />} />
        <StatCard label="예약 실행 중" value={activeScheduled} sub="트레이에서 주기적 실행" icon={<Timer size={18} />} />
        <StatCard label="오늘 실행" value={runsToday.length} sub={`총 ${runs.length}건 기록`} icon={<CheckCircle2 size={18} />} />
        <StatCard
          label="최근 성공률"
          value={successRate === null ? "-" : `${successRate}%`}
          sub="최근 30건 기준"
          icon={<Percent size={18} />}
        />
      </div>

      <section className="card">
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h2 className="text-[15px] font-semibold">최근 실행</h2>
          <button type="button" className="btn-ghost !h-7 !text-xs" onClick={() => navigate("history")}>
            전체 보기
          </button>
        </div>
        {runs.length === 0 ? (
          <div className="px-5 pb-5">
            <EmptyState
              icon={<Play size={20} />}
              title="아직 실행 기록이 없습니다"
              description="작업을 만들고 첫 내보내기를 실행해 보세요. 예약을 켜면 자동으로 실행됩니다."
              action={
                <button type="button" className="btn-primary mt-1" onClick={() => navigate("jobs")}>
                  작업 목록으로
                </button>
              }
            />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-faint border-b border-border">
                <th className="px-5 py-2 font-medium">작업</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 font-medium">내보냄/전체</th>
                <th className="px-3 py-2 font-medium">시작</th>
                <th className="px-3 py-2 font-medium">소요</th>
                <th className="px-5 py-2 font-medium text-right">트리거</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 6).map((run) => (
                <tr key={run.id} className="border-b border-border/60 last:border-0 hover:bg-raised/50">
                  <td className="px-5 py-2.5 font-medium truncate max-w-[220px]">{run.job_name}</td>
                  <td className="px-3 py-2.5"><StatusChip status={run.status} /></td>
                  <td className="px-3 py-2.5 text-muted tabular-nums">
                    {run.stats.pages_exported}/{run.stats.pages_total}
                  </td>
                  <td className="px-3 py-2.5 text-muted whitespace-nowrap">{formatDateTime(run.started_at)}</td>
                  <td className="px-3 py-2.5 text-muted tabular-nums">{formatDuration(run.started_at, run.finished_at)}</td>
                  <td className="px-5 py-2.5 text-right text-xs text-faint">
                    {run.trigger === "scheduled" ? "예약" : "수동"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {!connected && (
        <div className="card border-warn/40 bg-warn/5 px-5 py-4 flex items-center justify-between gap-4">
          <div className="text-sm">
            <div className="font-semibold text-warn">Confluence 연결이 필요합니다</div>
            <div className="text-xs text-muted mt-0.5">연결 화면에서 Base URL, 이메일, API 토큰을 저장하세요.</div>
          </div>
          <button type="button" className="btn-secondary shrink-0" onClick={() => navigate("connections")}>
            연결하러 가기
          </button>
        </div>
      )}

      <QuickRun jobs={jobs} onRun={openRunModal} />
    </div>
  );
}

function QuickRun({ jobs, onRun }: { jobs: { id: string; name: string }[]; onRun: (id: string) => void }) {
  if (jobs.length === 0) return null;
  return (
    <section className="card px-5 py-4">
      <h2 className="text-[15px] font-semibold mb-3">빠른 실행</h2>
      <div className="flex flex-wrap gap-2">
        {jobs.slice(0, 6).map((job) => (
          <button
            key={job.id}
            type="button"
            className="btn-secondary"
            onClick={() => onRun(job.id)}
            title={`${job.name} 즉시 실행`}
          >
            <Play size={13} /> {job.name}
          </button>
        ))}
      </div>
    </section>
  );
}
