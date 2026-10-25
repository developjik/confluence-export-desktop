import { useState } from "react";
import { Loader2, Save, ShieldCheck } from "lucide-react";
import { api, toAppError } from "../ipc";
import { useStore } from "../store";
import { Field, SectionCard } from "../components/ui";
import type { AppSettings } from "../types";

export default function SettingsScreen() {
  const { snapshot, refresh, pushToast } = useStore();
  const [draft, setDraft] = useState<AppSettings>(
    snapshot?.settings ?? { base_url: "", email: "", theme: "system", log_level: "info", default_max_requests: 8 },
  );
  const [saving, setSaving] = useState(false);

  const patch = (partial: Partial<AppSettings>) => setDraft((prev) => ({ ...prev, ...partial }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveSettings(draft);
      await refresh();
      pushToast("ok", "설정을 저장했습니다.");
    } catch (err) {
      pushToast("err", toAppError(err).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-5">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">설정</h1>
          <p className="text-sm text-muted mt-1">앱 동작과 외관을 설정합니다.</p>
        </div>
        <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          저장
        </button>
      </header>

      <SectionCard number={1} title="일반">
        <div className="space-y-4">
          <Field label="테마">
            <select className="input" value={draft.theme} onChange={(e) => patch({ theme: e.target.value })}>
              <option value="system">시스템 설정 따르기</option>
              <option value="light">라이트</option>
              <option value="dark">다크</option>
            </select>
          </Field>
          <Field label="로그 레벨" hint="앱 로그는 앱 데이터 폴더의 logs/app.log에 기록됩니다.">
            <select className="input" value={draft.log_level} onChange={(e) => patch({ log_level: e.target.value })}>
              <option value="error">error</option>
              <option value="warn">warn</option>
              <option value="info">info</option>
              <option value="debug">debug</option>
              <option value="trace">trace</option>
            </select>
          </Field>
          <Field label="기본 동시 요청 수" hint="새 작업 생성 시 기본으로 사용됩니다.">
            <input
              className="input"
              type="number"
              min={1}
              max={32}
              value={draft.default_max_requests}
              onChange={(e) => patch({ default_max_requests: Number(e.target.value) || 8 })}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard number={2} title="정보">
        <div className="space-y-2 text-sm text-muted">
          <div className="flex items-center justify-between">
            <span>버전</span>
            <span className="font-mono text-text">{snapshot?.app_version}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>연결 상태</span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={13} className={snapshot?.has_token ? "text-ok" : "text-faint"} />
              {snapshot?.has_token ? "토큰 저장됨" : "미연결"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>엔진</span>
            <span className="text-text">Rust · Atlassian REST API 직접 연동</span>
          </div>
          <p className="text-xs text-faint leading-relaxed pt-2">
            v2는 confluence-markdown-exporter 없이 자체 Rust 엔진으로 문서를 변환합니다. 기존 v1 워크스페이스는 lockfile
            형식이 달라 첫 실행 시 전체 재동기화됩니다.
          </p>
        </div>
      </SectionCard>
    </div>
  );
}
