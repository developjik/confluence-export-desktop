import { useMemo, useState } from "react";
import { FolderOpen, Loader2, Save, X } from "lucide-react";
import { api, isTauri, toAppError } from "../ipc";
import { useStore } from "../store";
import { ErrorBanner, Field, SectionCard, ToggleRow } from "../components/ui";
import { HREF_MODE_LABELS, SCOPE_LABELS, WEEKDAY_LABELS, type HrefMode, type Job, type Scope } from "../types";

export default function JobEditor({ job }: { job: Job }) {
  const { closeEditor, refresh, pushToast, snapshot } = useStore();
  const [draft, setDraft] = useState<Job>(job);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [timesText, setTimesText] = useState(job.schedule.times.join(", "));

  const patch = (partial: Partial<Job>) => setDraft((prev) => ({ ...prev, ...partial }));
  const patchOptions = (partial: Partial<Job["export_options"]>) =>
    setDraft((prev) => ({ ...prev, export_options: { ...prev.export_options, ...partial } }));
  const patchSchedule = (partial: Partial<Job["schedule"]>) =>
    setDraft((prev) => ({ ...prev, schedule: { ...prev.schedule, ...partial } }));

  const scopePreview = useMemo(() => {
    const first = (draft.export_options.urls || draft.confluence_url || "").split(/[\s,]+/)[0] ?? "";
    if (!first) return "URL을 입력하면 범위가 표시됩니다.";
    if (first.includes("/pages/")) {
      return draft.include_children ? "하위 페이지 포함(pages-with-descendants)" : "단일 페이지(pages)";
    }
    if (first.includes("/spaces/") || /\/wiki\/[A-Z][A-Z0-9]*~?$/i.test(first)) {
      return "스페이스 전체(spaces)";
    }
    return "사이트 전체(orgs)";
  }, [draft.export_options.urls, draft.confluence_url, draft.include_children]);

  const pickFolder = async () => {
    if (!isTauri) {
      patch({ target_dir: draft.target_dir || "/Users/user/Documents/confluence-export" });
      return;
    }
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ directory: true, multiple: false, title: "대상 폴더 선택" });
    if (typeof selected === "string") {
      patch({ target_dir: selected });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const normalized: Job = {
        ...draft,
        name: draft.name.trim(),
        target_dir: draft.target_dir.trim(),
        export_options: {
          ...draft.export_options,
          urls: (draft.export_options.urls || draft.confluence_url).trim(),
        },
        schedule: {
          ...draft.schedule,
          times: timesText
            .split(",")
            .map((t) => t.trim())
            .filter((t) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t)),
        },
      };
      if (normalized.schedule.times.length === 0) {
        normalized.schedule.times = ["09:00"];
      }
      const saved = await api.saveJob(normalized);
      await refresh();
      pushToast("ok", `작업 "${saved.name}"을(를) 저장했습니다.`);
      closeEditor();
    } catch (err) {
      const appErr = toAppError(err);
      setError(`${appErr.message}${appErr.detail ? ` — ${appErr.detail}` : ""}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-5 animate-fade-in">
      <header className="flex items-end justify-between gap-4 sticky top-0 z-10 bg-bg py-1">
        <div>
          <h1 className="text-xl font-bold tracking-tight">{job.id ? "작업 편집" : "새 작업"}</h1>
          <p className="text-sm text-muted mt-1">내보내기 범위와 옵션, 예약을 설정합니다.</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={closeEditor}>
            <X size={14} /> 취소
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || !draft.name.trim()}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            저장
          </button>
        </div>
      </header>

      <ErrorBanner message={error} />

      <SectionCard number={1} title="기본 정보">
        <div className="space-y-4">
          <Field label="작업 이름">
            <input
              className="input"
              value={draft.name}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="예: 제품 문서 스페이스"
            />
          </Field>
          <Field label="대상 폴더" hint="내보낸 Markdown과 첨부파일이 저장되는 폴더입니다.">
            <div className="flex gap-2">
              <input
                className="input"
                value={draft.target_dir}
                onChange={(e) => patch({ target_dir: e.target.value })}
                placeholder="폴더를 선택하거나 경로를 입력하세요"
              />
              <button type="button" className="btn-secondary shrink-0" onClick={pickFolder}>
                <FolderOpen size={14} /> 선택
              </button>
            </div>
          </Field>
          <ToggleRow label="작업 사용" description="끄면 예약 실행에서 제외됩니다." checked={draft.enabled} onChange={(v) => patch({ enabled: v })} />
        </div>
      </SectionCard>

      <SectionCard number={2} title="범위" description="내보낼 Confluence URL과 해석 규칙을 정합니다.">
        <div className="space-y-4">
          <Field label="Confluence URL" hint="페이지, 스페이스, 사이트 URL을 쉼표나 줄바꿈으로 구분해 여러 개 입력할 수 있습니다.">
            <textarea
              className="textarea !font-sans"
              rows={2}
              value={draft.export_options.urls || draft.confluence_url}
              onChange={(e) => patchOptions({ urls: e.target.value })}
              placeholder="https://team.atlassian.net/wiki/spaces/PROD"
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="범위">
              <select
                className="input"
                value={draft.export_options.scope}
                onChange={(e) => patchOptions({ scope: e.target.value as Scope })}
              >
                {Object.entries(SCOPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label} ({value})
                  </option>
                ))}
              </select>
            </Field>
            <div className="flex items-end">
              <div className="w-full rounded-lg border border-border bg-raised/60 px-3 py-2 text-xs text-muted">
                {draft.export_options.scope === "auto" ? scopePreview : `${SCOPE_LABELS[draft.export_options.scope]} 범위로 실행됩니다.`}
              </div>
            </div>
          </div>
          <ToggleRow
            label="하위 페이지 포함"
            description="자동 범위에서 페이지 URL일 때 하위 페이지까지 내보낼지 결정합니다."
            checked={draft.include_children}
            onChange={(v) => patch({ include_children: v })}
          />
        </div>
      </SectionCard>

      <SectionCard number={3} title="콘텐츠 옵션">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Field label="페이지 링크 형식">
              <select
                className="input"
                value={draft.export_options.page_link}
                onChange={(e) => patchOptions({ page_link: e.target.value as HrefMode })}
              >
                {Object.entries(HREF_MODE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="첨부파일 링크 형식">
              <select
                className="input"
                value={draft.export_options.attachment_link}
                onChange={(e) => patchOptions({ attachment_link: e.target.value as HrefMode })}
              >
                {Object.entries(HREF_MODE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="divide-y divide-border/70">
            <ToggleRow
              label="첨부파일 전체 저장"
              description="본문에서 참조되지 않은 첨부파일도 모두 내보냅니다."
              checked={draft.export_options.attachment_export_all}
              onChange={(v) => patchOptions({ attachment_export_all: v })}
            />
            <ToggleRow
              label="이동 경로(breadcrumbs) 표시"
              description="문서 상단에 스페이스/상위 페이지 경로를 추가합니다."
              checked={draft.export_options.page_breadcrumbs}
              onChange={(v) => patchOptions({ page_breadcrumbs: v })}
            />
            <ToggleRow
              label="페이지 속성을 Front Matter로"
              description="페이지 속성 매크로를 YAML front matter로 변환합니다."
              checked={draft.export_options.page_properties_as_front_matter}
              onChange={(v) => patchOptions({ page_properties_as_front_matter: v })}
            />
            <ToggleRow
              label="표준 메타데이터 Front Matter"
              description="제목·URL·스페이스·버전을 front matter에 포함합니다."
              checked={draft.export_options.front_matter_standard}
              onChange={(v) => patchOptions({ front_matter_standard: v })}
            />
            <ToggleRow
              label="문서 제목 헤딩 포함"
              description="본문 첫 줄에 # 제목을 추가합니다."
              checked={draft.export_options.include_document_title}
              onChange={(v) => patchOptions({ include_document_title: v })}
            />
            <ToggleRow
              label="변경 없는 페이지 건너뛰기"
              description="버전이 변경되지 않은 페이지는 다시 쓰지 않습니다."
              checked={draft.export_options.skip_unchanged}
              onChange={(v) => patchOptions({ skip_unchanged: v })}
            />
            <ToggleRow
              label="사라진 파일 정리"
              description="삭제/이동된 페이지의 로컬 파일을 제거합니다(전체 범위 실행 시)."
              checked={draft.export_options.cleanup_stale}
              onChange={(v) => patchOptions({ cleanup_stale: v })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="동시 요청 수" hint={`기본값: ${snapshot?.settings.default_max_requests ?? 8}`}>
              <input
                className="input"
                type="number"
                min={1}
                max={32}
                value={draft.export_options.max_requests}
                onChange={(e) => patchOptions({ max_requests: Number(e.target.value) || 1 })}
              />
            </Field>
            <Field label="요청 타임아웃(초)">
              <input
                className="input"
                type="number"
                min={5}
                max={300}
                value={draft.export_options.timeout_seconds}
                onChange={(e) => patchOptions({ timeout_seconds: Number(e.target.value) || 30 })}
              />
            </Field>
          </div>
        </div>
      </SectionCard>

      <SectionCard number={4} title="고급" description="출력 경로 템플릿과 세부 규칙을 조정합니다.">
        <div className="space-y-4">
          <Field
            label="페이지 경로 템플릿"
            hint="사용 가능: {space_name} {space_key} {homepage_title} {ancestor_titles} {page_title}"
          >
            <input
              className="input font-mono !text-xs"
              value={draft.export_options.page_path}
              onChange={(e) => patchOptions({ page_path: e.target.value })}
            />
          </Field>
          <Field
            label="첨부파일 경로 템플릿"
            hint="사용 가능: {space_name} {space_key} {attachment_file_id} {attachment_file_name} {attachment_extension}"
          >
            <input
              className="input font-mono !text-xs"
              value={draft.export_options.attachment_path}
              onChange={(e) => patchOptions({ attachment_path: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="파일명 최대 길이">
              <input
                className="input"
                type="number"
                min={16}
                max={200}
                value={draft.export_options.filename_max_length}
                onChange={(e) => patchOptions({ filename_max_length: Number(e.target.value) || 120 })}
              />
            </Field>
            <Field label="고급 JSON (v1 호환)" hint="형식만 검증되며 v2에서는 대부분 무시됩니다.">
              <textarea
                className="textarea"
                rows={1}
                value={draft.export_options.config_json}
                onChange={(e) => patchOptions({ config_json: e.target.value })}
                placeholder="{}"
              />
            </Field>
          </div>
        </div>
      </SectionCard>

      <SectionCard number={5} title="예약" description="앱이 트레이에서 실행 중일 때 주기적으로 내보냅니다.">
        <div className="space-y-4">
          <ToggleRow
            label="예약 사용"
            checked={draft.schedule.enabled}
            onChange={(v) => patchSchedule({ enabled: v })}
          />
          <div className="grid grid-cols-2 gap-4">
            <Field label="반복 주기">
              <select
                className="input"
                value={draft.schedule.kind}
                onChange={(e) =>
                  patchSchedule({ kind: e.target.value as Job["schedule"]["kind"] })
                }
              >
                <option value="daily">매일</option>
                <option value="weekly">매주 (요일 선택)</option>
                <option value="monthly">매월 (날짜 지정)</option>
              </select>
            </Field>
            <Field label="실행 시각" hint="쉼표로 구분해 여러 시각을 지정할 수 있습니다. 예: 09:00, 18:30">
              <input className="input" value={timesText} onChange={(e) => setTimesText(e.target.value)} placeholder="09:00" />
            </Field>
          </div>
          {draft.schedule.kind === "weekly" && (
            <div>
              <span className="label">요일</span>
              <div className="flex gap-1.5">
                {WEEKDAY_LABELS.map((label, idx) => {
                  const day = idx + 1;
                  const active = draft.schedule.days_of_week.includes(day);
                  return (
                    <button
                      key={day}
                      type="button"
                      onClick={() =>
                        patchSchedule({
                          days_of_week: active
                            ? draft.schedule.days_of_week.filter((d) => d !== day)
                            : [...draft.schedule.days_of_week, day].sort(),
                        })
                      }
                      className={`h-9 w-10 rounded-lg border text-sm font-medium transition-colors ${
                        active
                          ? "border-accent bg-accent/10 text-accent"
                          : "border-border text-muted hover:bg-raised"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {draft.schedule.kind === "monthly" && (
            <Field label="매월 몇 일" hint="짧은 달에는 해당 달의 마지막 날로 조정됩니다.">
              <input
                className="input"
                type="number"
                min={1}
                max={31}
                value={draft.schedule.day_of_month ?? 1}
                onChange={(e) => patchSchedule({ day_of_month: Number(e.target.value) || 1 })}
              />
            </Field>
          )}
          <Field label="시간대">
            <select
              className="input"
              value={draft.schedule.timezone}
              onChange={(e) => patchSchedule({ timezone: e.target.value })}
            >
              {["Asia/Seoul", "Asia/Tokyo", "UTC", "America/Los_Angeles", "Europe/London"].map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </Field>
          <ToggleRow
            label="일시 정지"
            description="예약은 유지하되 실행을 잠시 멈춥니다."
            checked={draft.schedule.paused}
            onChange={(v) => patchSchedule({ paused: v })}
          />
        </div>
      </SectionCard>
    </div>
  );
}
