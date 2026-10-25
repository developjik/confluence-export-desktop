import { useState } from "react";
import { ChevronDown, History, RefreshCw } from "lucide-react";
import { formatDateTime, formatDuration, useStore } from "../store";
import { EmptyState, StatusChip } from "../components/ui";

export default function RunHistory() {
  const { snapshot, refresh } = useStore();
  const runs = snapshot?.runs ?? [];
  const jobs = snapshot?.jobs ?? [];
  const [jobFilter, setJobFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = jobFilter === "all" ? runs : runs.filter((r) => r.job_id === jobFilter);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">실행 기록</h1>
          <p className="text-sm text-muted mt-1">최근 400건의 실행 기록이 저장됩니다.</p>
        </div>
        <div className="flex items-center gap-2">
          <select className="input !w-auto" value={jobFilter} onChange={(e) => setJobFilter(e.target.value)}>
            <option value="all">전체 작업</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>
                {job.name}
              </option>
            ))}
          </select>
          <button type="button" className="btn-secondary" onClick={() => refresh()}>
            <RefreshCw size={14} /> 새로고침
          </button>
        </div>
      </header>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<History size={20} />}
          title="실행 기록이 없습니다"
          description="작업을 실행하면 결과와 통계가 여기에 쌓입니다."
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-faint border-b border-border bg-raised/40">
                <th className="px-4 py-2.5 font-medium w-8" />
                <th className="px-2 py-2.5 font-medium">시작</th>
                <th className="px-2 py-2.5 font-medium">작업</th>
                <th className="px-2 py-2.5 font-medium">상태</th>
                <th className="px-2 py-2.5 font-medium text-right">내보냄</th>
                <th className="px-2 py-2.5 font-medium text-right">건너뜀</th>
                <th className="px-2 py-2.5 font-medium text-right">실패</th>
                <th className="px-2 py-2.5 font-medium">소요</th>
                <th className="px-4 py-2.5 font-medium">트리거</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((run) => (
                <>
                  <tr
                    key={run.id}
                    className="border-b border-border/60 last:border-0 hover:bg-raised/50 cursor-pointer"
                    onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                  >
                    <td className="px-4 py-2.5 text-faint">
                      <ChevronDown
                        size={14}
                        className={`transition-transform ${expanded === run.id ? "rotate-180" : ""}`}
                      />
                    </td>
                    <td className="px-2 py-2.5 text-muted whitespace-nowrap">{formatDateTime(run.started_at)}</td>
                    <td className="px-2 py-2.5 font-medium truncate max-w-[200px]">{run.job_name}</td>
                    <td className="px-2 py-2.5"><StatusChip status={run.status} /></td>
                    <td className="px-2 py-2.5 text-right tabular-nums">{run.stats.pages_exported}</td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-muted">{run.stats.pages_skipped}</td>
                    <td className={`px-2 py-2.5 text-right tabular-nums ${run.stats.pages_failed > 0 ? "text-err font-semibold" : "text-muted"}`}>
                      {run.stats.pages_failed}
                    </td>
                    <td className="px-2 py-2.5 text-muted tabular-nums whitespace-nowrap">
                      {formatDuration(run.started_at, run.finished_at)}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-faint">{run.trigger === "scheduled" ? "예약" : "수동"}</td>
                  </tr>
                  {expanded === run.id && (
                    <tr key={`${run.id}-detail`} className="bg-raised/30 border-b border-border/60">
                      <td colSpan={9} className="px-8 py-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          <DetailItem label="범위" value={run.scope} />
                          <DetailItem label="전체 페이지" value={String(run.stats.pages_total)} />
                          <DetailItem label="첨부파일 내보냄" value={`${run.stats.attachments_exported}/${run.stats.attachments_total}`} />
                          <DetailItem label="정리된 파일" value={String(run.stats.files_removed)} />
                        </div>
                        <div className="mt-3 text-xs text-muted">
                          <div className="font-medium text-faint mb-1">대상 URL</div>
                          {run.urls.map((url) => (
                            <div key={url} className="font-mono break-all">{url}</div>
                          ))}
                          <div className="font-medium text-faint mt-2 mb-1">대상 폴더</div>
                          <div className="font-mono break-all">{run.target_dir}</div>
                          {run.error && (
                            <>
                              <div className="font-medium text-err mt-2 mb-1">오류</div>
                              <div className="text-err">{run.error}</div>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface border border-border px-3 py-2">
      <div className="text-[11px] text-faint font-medium">{label}</div>
      <div className="font-semibold mt-0.5">{value}</div>
    </div>
  );
}
