import { type ReactNode } from "react";
import { Loader2, RefreshCw, ServerOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { cn } from "@/lib/format";
import type { RiskFlag, SourceType } from "@/lib/types";

/* ------------------------------ layout ------------------------------ */

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-8 flex items-end justify-between gap-6">
      <div className="min-w-0">
        <h1 className="font-serif text-[28px] font-semibold leading-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
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
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/* ------------------------------ status ------------------------------ */

const STATUS: Record<string, string> = {
  draft: "bg-white/5 text-muted ring-white/10",
  generated: "bg-sky-400/10 text-sky-300 ring-sky-400/20",
  approved: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  scheduled: "bg-brand-500/15 text-brand-300 ring-brand-500/25",
  published: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  failed: "bg-rose-400/10 text-rose-300 ring-rose-400/20",
  rejected: "bg-transparent text-rose-300 ring-rose-400/30",
  queued: "bg-white/5 text-muted ring-white/10",
  rendering: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
  ready: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
};

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1", STATUS[status] ?? STATUS.draft)}>
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
  };
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <span className={cn("h-1.5 w-1.5 rounded-full", mode === "gemini" ? "bg-brand-400" : "bg-muted/60")} />
      {label[mode] ?? mode}
    </span>
  );
}

/** Data provenance for metrics. Simulated is deliberately loud. */
export function SourceBadge({ source }: { source: SourceType | string }) {
  if (source === "simulated")
    return <span className="rounded-md bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-300 ring-1 ring-amber-400/30">Simulated</span>;
  const label = source === "imported_csv" ? "Imported CSV" : source.startsWith("api:") ? source.slice(4) : source;
  return <span className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-white/10">{label}</span>;
}

const SEVERITY = {
  info: "bg-sky-300",
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
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-16 text-center">
      {icon && <div className="mb-4 text-muted">{icon}</div>}
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-muted">{hint}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-rose-400/20 bg-rose-400/5 px-5 py-4 text-sm">
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
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-white/5 text-muted ring-1 ring-white/10">
        <ServerOff className="h-6 w-6" />
      </div>
      <h2 className="text-lg font-semibold text-ink">The AdPilot API isn't reachable</h2>
      <p className="mt-2 text-sm text-muted">
        This app reads everything from the FastAPI backend at <span className="font-mono text-ink/80">{API_URL}</span>. Start it, then try again.
      </p>
      <pre className="mt-5 w-full rounded-lg bg-black/30 px-4 py-3 text-left font-mono text-xs text-ink/80 ring-1 ring-white/10">
        cd backend{"\n"}uvicorn app.main:app --reload --port 8000
      </pre>
      <button onClick={onRetry} className="btn-ghost mt-5">
        <RefreshCw className="h-4 w-4" /> Try again
      </button>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-white/5", className)} />;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} />;
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-md bg-white/5 px-2.5 py-1 text-xs text-ink/80 ring-1 ring-white/10", className)}>{children}</span>;
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
