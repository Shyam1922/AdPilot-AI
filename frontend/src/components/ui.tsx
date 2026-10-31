import { useEffect, useState, type ReactNode } from "react";
import { Loader2, Pencil, RefreshCw, ServerOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { cn } from "@/lib/format";
import type { RiskFlag, SourceType } from "@/lib/types";

/* ------------------------------ layout ------------------------------ */

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0 max-w-full">
        <h1 className="display text-[32px] leading-[1.1] sm:text-[40px]">{title}</h1>
        {subtitle && <p className="mt-3 text-[15px] text-muted">{subtitle}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("card p-6", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-[15px] font-medium text-white">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/* ------------------------------ status ------------------------------ */

const STATUS: Record<string, string> = {
  draft: "bg-raised text-muted ring-transparent",
  generated: "bg-raised text-body ring-transparent",
  approved: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  scheduled: "bg-white text-black ring-transparent",
  published: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  failed: "bg-rose-400/10 text-rose-300 ring-rose-400/20",
  rejected: "bg-transparent text-rose-300 ring-rose-400/30",
  queued: "bg-raised text-muted ring-transparent",
  rendering: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
  ready: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-medium capitalize ring-1", STATUS[status] ?? STATUS.draft)}>
      {status}
    </span>
  );
}

/** Where an AI output came from: gemini / offline / template video variants. */
export function ModeBadge({ mode }: { mode: string }) {
  const label: Record<string, string> = {
    gemini: "Gemini",
    offline: "Offline generator",
    template: "Template video",
    "template+ai_broll": "Template + AI b-roll",
    "template+tts": "Template + voiceover",
    rules: "Rules",
    "rules+gemini": "Rules + Gemini",
    "rules+offline": "Rules + offline generator",
  };
  const fallback = mode.replace(/_/g, " ").replace(/\+/g, " + ").replace(/^\w/, (c) => c.toUpperCase());
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <span className={cn("h-1.5 w-1.5 rounded-full", mode.includes("gemini") ? "bg-white" : "bg-muted/60")} />
      {label[mode] ?? fallback}
    </span>
  );
}

/** Data provenance for metrics. Simulated is deliberately loud. */
export function SourceBadge({ source }: { source: SourceType | string }) {
  if (source === "simulated")
    return <span className="rounded-md bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-300 ring-1 ring-amber-400/30">Simulated</span>;
  const label = source === "imported_csv" ? "Imported CSV" : source.startsWith("api:") ? source.slice(4) : source;
  return <span className="rounded-md bg-raised px-2 py-0.5 text-[11px] font-medium text-body">{label}</span>;
}

const SEVERITY = {
  info: "bg-white/50",
  warn: "bg-amber-300",
  block: "bg-rose-400",
};

export function RiskFlags({ flags }: { flags: RiskFlag[] }) {
  if (!flags.length) return null;
  return (
    <ul className="space-y-2">
      {flags.map((f, i) => (
        <li key={i} className="flex items-start gap-2.5 text-sm">
          <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", SEVERITY[f.severity])} />
          <span className="text-ink/90">
            {f.message}
            <span className="ml-2 font-mono text-[11px] text-muted">
              {f.code}
              {f.field ? ` · ${f.field}` : ""}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------ states ------------------------------ */

export function EmptyState({ title, hint, action, icon }: { title: string; hint: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-line bg-white/[0.02] px-6 py-16 text-center">
      {icon && <div className="mb-4 text-muted">{icon}</div>}
      <p className="text-[17px] font-medium text-white">{title}</p>
      <p className="mt-2 max-w-sm text-sm text-muted">{hint}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 px-5 py-4 text-sm">
      <p className="text-rose-200">{error instanceof Error ? error.message : "Something went wrong."}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-3 inline-flex items-center gap-1.5 text-rose-200 hover:text-white">
          <RefreshCw className="h-3.5 w-3.5" /> Try again
        </button>
      )}
    </div>
  );
}

export function ApiOffline({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-24 text-center">
      <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-xl bg-raised text-muted">
        <ServerOff className="h-6 w-6" />
      </div>
      <h2 className="display text-[32px] leading-tight">The API isn't reachable</h2>
      <p className="mt-2 text-sm text-muted">
        This app reads everything from the FastAPI backend at <span className="font-mono text-ink/80">{API_URL}</span>. Start it, then try again.
      </p>
      <pre className="mt-6 w-full rounded-xl border border-line bg-surface px-4 py-3 text-left font-mono text-xs text-body">
        cd backend{"\n"}uvicorn app.main:app --reload --port 8000
      </pre>
      <button onClick={onRetry} className="btn-primary mt-6">
        <RefreshCw className="h-4 w-4" /> Try again
      </button>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-2xl bg-surface", className)} />;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} />;
}

/** Suspense fallback while a lazily loaded page arrives. */
export function PageFallback() {
  return (
    <div className="flex justify-center py-24 text-muted">
      <Spinner className="h-5 w-5" />
    </div>
  );
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-lg bg-raised px-2.5 py-1 text-xs text-body", className)}>{children}</span>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** A heading that turns into an input: Enter or blur saves, Escape cancels. */
export function EditableTitle({ value, label, saving, onSave }: { value: string; label: string; saving?: boolean; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);

  const commit = () => {
    const v = draft.trim();
    setEditing(false);
    if (v && v !== value) onSave(v);
    else setDraft(value);
  };

  if (editing)
    return (
      <input
        autoFocus
        aria-label={label}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
        style={{ font: "inherit", letterSpacing: "inherit" }}
        className="-mx-2 w-full min-w-0 rounded-xl border border-white/25 bg-transparent px-2 text-white outline-none"
      />
    );

  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span className="truncate">{value}</span>
      <button
        onClick={() => setEditing(true)}
        disabled={saving}
        aria-label={label}
        title={label}
        className="shrink-0 rounded-lg p-1.5 text-muted transition hover:bg-white/5 hover:text-white"
      >
        {saving ? <Spinner /> : <Pencil className="h-4 w-4" />}
      </button>
    </span>
  );
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  pending,
  onConfirm,
  onClose,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !pending && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, pending]);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={() => !pending && onClose()}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[#16171a] p-6 shadow-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="display text-[26px] leading-tight">{title}</h2>
        <div className="mt-2 text-sm text-muted">{body}</div>
        <div className="mt-6 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button className="btn bg-danger text-black hover:bg-red-300" onClick={onConfirm} disabled={pending} autoFocus>
            {pending && <Spinner />} {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
