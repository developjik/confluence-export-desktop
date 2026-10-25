import { useState } from "react";
import { ArrowDownToLine, CheckCircle2, Eye, EyeOff, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { api, toAppError } from "../ipc";
import { useStore } from "../store";
import { ErrorBanner, Field } from "../components/ui";

export default function Connections() {
  const { snapshot, refresh, pushToast } = useStore();
  const settings = snapshot?.settings;
  const [baseUrl, setBaseUrl] = useState(settings?.base_url ?? "");
  const [email, setEmail] = useState(settings?.email ?? "");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [error, setError] = useState("");

  const connected = Boolean(snapshot?.has_token && settings?.base_url);

  const handleTest = async () => {
    setTesting(true);
    setError("");
    setTestResult(null);
    try {
      const result = await api.testConnection(baseUrl, email, token);
      setTestResult({ ok: true, text: `연결 성공 — ${result.display_name}${result.email ? ` (${result.email})` : ""}` });
    } catch (err) {
      const appErr = toAppError(err);
      setTestResult({ ok: false, text: appErr.message });
      setError(appErr.detail || appErr.message);
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await api.saveConnection(baseUrl, email, token);
      setToken("");
      await refresh();
      pushToast("ok", "연결 정보를 저장했습니다.");
    } catch (err) {
      const appErr = toAppError(err);
      setError(`${appErr.message}${appErr.detail ? ` (${appErr.detail})` : ""}`);
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    await api.clearToken();
    await refresh();
    pushToast("info", "저장된 API 토큰을 삭제했습니다.");
  };

  const handleImportV1 = async () => {
    setImporting(true);
    try {
      const summary = await api.importV1();
      const parts: string[] = [];
      if (summary.settings_imported) parts.push("연결 설정");
      if (summary.jobs_imported > 0) parts.push(`작업 ${summary.jobs_imported}개`);
      if (summary.token_imported) parts.push("API 토큰");
      await refresh();
      if (parts.length === 0) {
        pushToast("info", "가져올 v1 설정을 찾지 못했습니다.");
      } else {
        pushToast("ok", `v1에서 ${parts.join(", ")}를 가져왔습니다.`);
      }
    } catch (err) {
      const appErr = toAppError(err);
      pushToast("err", `가져오기 실패: ${appErr.message}`);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <header>
        <h1 className="text-xl font-bold tracking-tight">연결</h1>
        <p className="text-sm text-muted mt-1">
          Confluence Cloud 인증 정보를 저장합니다. 토큰은 OS 자격증명 저장소(Windows 자격 증명 관리자 / macOS 키체인)에만
          보관되며 파일로 저장되지 않습니다.
        </p>
      </header>

      <div className="card px-6 py-5 space-y-4">
        <div className="flex items-center gap-2 text-sm">
          <ShieldCheck size={16} className={connected ? "text-ok" : "text-faint"} />
          {connected ? (
            <span>
              <span className="font-semibold">{settings?.email}</span>
              <span className="text-muted"> · {settings?.base_url} · 토큰 저장됨</span>
            </span>
          ) : (
            <span className="text-muted">저장된 연결이 없습니다.</span>
          )}
        </div>

        <ErrorBanner message={error} />

        <Field label="Confluence Base URL" hint="예: https://team.atlassian.net">
          <input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://team.atlassian.net" />
        </Field>

        <Field label="이메일">
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@team.io" />
        </Field>

        <Field
          label="API 토큰"
          hint={
            <>
              id.atlassian.com/manage-profile/security/api-tokens 에서 생성할 수 있습니다. 저장 후에는 다시 입력하지
              않아도 됩니다.
            </>
          }
        >
          <div className="relative">
            <input
              className="input pr-10"
              type={showToken ? "text" : "password"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="API 토큰 입력"
              autoComplete="off"
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-faint hover:text-muted"
              onClick={() => setShowToken((v) => !v)}
              aria-label="토큰 표시"
            >
              {showToken ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </Field>

        {testResult && (
          <div
            className={`rounded-lg border px-4 py-2.5 text-sm flex items-center gap-2 ${
              testResult.ok ? "border-ok/40 bg-ok/10 text-ok" : "border-err/40 bg-err/10 text-err"
            }`}
          >
            {testResult.ok ? <CheckCircle2 size={15} /> : <Trash2 size={15} className="rotate-45" />}
            {testResult.text}
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={handleTest} disabled={testing || !baseUrl || !email || !token}>
            {testing && <Loader2 size={14} className="animate-spin" />}
            연결 테스트
          </button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || !baseUrl || !email || !token}>
            {saving && <Loader2 size={14} className="animate-spin" />}
            저장
          </button>
          {connected && (
            <button type="button" className="btn-danger ml-auto" onClick={handleClear}>
              <Trash2 size={14} /> 토큰 삭제
            </button>
          )}
        </div>
      </div>

      <div className="card px-6 py-5">
        <h2 className="text-[15px] font-semibold">v1에서 가져오기</h2>
        <p className="text-xs text-faint mt-1 mb-3 leading-relaxed">
          v1(Confluence Export Desktop 1.x)의 작업과 연결 설정을 가져옵니다. Windows에서는 자격 증명 관리자에 저장된 API
          토큰도 함께 이관됩니다. macOS에서는 토큰을 다시 입력해야 합니다.
        </p>
        <button type="button" className="btn-secondary" onClick={handleImportV1} disabled={importing}>
          {importing ? <Loader2 size={14} className="animate-spin" /> : <ArrowDownToLine size={14} />}
          v1 설정 가져오기
        </button>
      </div>
    </div>
  );
}
