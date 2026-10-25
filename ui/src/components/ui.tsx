import React from "react";
import { X } from "lucide-react";
import type { RunStatus } from "../types";

export function StatusChip({ status }: { status: RunStatus | "scheduled" | "enabled" | "disabled" }) {
  const map: Record<string, { label: string; cls: string }> = {
    succeeded: { label: "성공", cls: "bg-ok/10 text-ok border-ok/30" },
    failed: { label: "실패", cls: "bg-err/10 text-err border-err/30" },
    running: { label: "실행 중", cls: "bg-warn/10 text-warn border-warn/30 animate-pulse-dot" },
    cancelled: { label: "취소됨", cls: "bg-muted/10 text-muted border-border" },
    scheduled: { label: "예약", cls: "bg-accent/10 text-accent border-accent/30" },
    enabled: { label: "사용", cls: "bg-ok/10 text-ok border-ok/30" },
    disabled: { label: "꺼짐", cls: "bg-muted/10 text-faint border-border" },
  };
  const entry = map[status] ?? map.disabled;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${entry.cls}`}>
      {status === "running" && <span className="h-1.5 w-1.5 rounded-full bg-warn" />}
      {entry.label}
    </span>
  );
}

export function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5.5 w-10 shrink-0 items-center rounded-full transition-colors
        ${checked ? "bg-accent" : "bg-strong"} disabled:opacity-50`}
      style={{ height: 22 }}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-[22px]" : "translate-x-[3px]"
        }`}
      />
    </button>
  );
}

export function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-2.5">
      <div className="min-w-0">
        <div className="text-sm font-medium text-text">{label}</div>
        {description && <div className="text-xs text-faint mt-0.5">{description}</div>}
      </div>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} />
      <div
        className={`relative card shadow-pop animate-fade-in w-full ${wide ? "max-w-3xl" : "max-w-lg"} max-h-[88vh] flex flex-col`}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <div className="text-base font-semibold">{title}</div>
          <button type="button" className="btn-ghost !h-8 !px-2" onClick={onClose} aria-label="닫기">
            <X size={16} />
          </button>
        </div>
        <div className="px-6 pb-6 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 px-8 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent">
        {icon}
      </div>
      <div className="text-base font-semibold">{title}</div>
      {description && <div className="max-w-sm text-sm text-muted leading-relaxed">{description}</div>}
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="card px-5 py-4 flex items-start gap-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-muted">{label}</div>
        <div className="text-2xl font-bold tracking-tight leading-tight mt-0.5">{value}</div>
        {sub && <div className="text-xs text-faint mt-0.5 truncate">{sub}</div>}
      </div>
    </div>
  );
}

export function SectionCard({
  number,
  title,
  description,
  children,
  actions,
}: {
  number: number;
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <section className="card px-6 py-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent/10 text-accent text-xs font-bold">
            {number}
          </span>
          <div>
            <h3 className="text-[15px] font-semibold leading-6">{title}</h3>
            {description && <p className="text-xs text-faint mt-0.5">{description}</p>}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="rounded-lg border border-err/40 bg-err/10 px-4 py-2.5 text-sm text-err">
      {message}
    </div>
  );
}
