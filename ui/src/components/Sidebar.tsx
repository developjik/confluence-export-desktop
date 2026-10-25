import {
  ArrowDownToLine,
  CalendarClock,
  FolderSync,
  History,
  LayoutDashboard,
  Plug,
  Settings,
} from "lucide-react";
import { useStore, type Screen } from "../store";

const NAV: { id: Screen; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "대시보드", icon: <LayoutDashboard size={18} /> },
  { id: "connections", label: "연결", icon: <Plug size={18} /> },
  { id: "jobs", label: "작업", icon: <FolderSync size={18} /> },
  { id: "history", label: "실행 기록", icon: <History size={18} /> },
  { id: "settings", label: "설정", icon: <Settings size={18} /> },
];

export default function Sidebar() {
  const { screen, navigate, snapshot } = useStore();
  const connected = Boolean(snapshot?.has_token && snapshot?.settings.base_url);
  const scheduled = snapshot?.jobs.filter((j) => j.enabled && j.schedule.enabled && !j.schedule.paused).length ?? 0;

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white">
          <ArrowDownToLine size={17} strokeWidth={2.4} />
        </div>
        <div className="leading-tight">
          <div className="text-[13.5px] font-bold tracking-tight">Confluence Export</div>
          <div className="text-[10.5px] text-faint font-medium">Desktop v{snapshot?.app_version ?? "…"}</div>
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {NAV.map((item) => {
          const active = screen === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => navigate(item.id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 h-9 text-[13.5px] font-medium transition-colors ${
                active ? "bg-accent/10 text-accent" : "text-muted hover:bg-raised hover:text-text"
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="p-3 space-y-2">
        {scheduled > 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-raised px-3 py-2 text-[11.5px] text-muted">
            <CalendarClock size={13} className="text-accent shrink-0" />
            예약 작업 {scheduled}개 실행 중
          </div>
        )}
        <button
          type="button"
          onClick={() => navigate("connections")}
          className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-[11.5px] text-muted hover:bg-raised transition-colors"
        >
          <span className={`h-2 w-2 rounded-full shrink-0 ${connected ? "bg-ok" : "bg-err"}`} />
          {connected ? (
            <span className="truncate">{snapshot?.settings.email}</span>
          ) : (
            <span className="text-warn font-medium">연결이 필요합니다</span>
          )}
        </button>
      </div>
    </aside>
  );
}
