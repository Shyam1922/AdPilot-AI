import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, Instagram, Linkedin, MessageSquare, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { Card, Skeleton, Spinner } from "@/components/ui";
import type { PlatformInsight, SocialPlatform } from "@/lib/types";

export const PLATFORM_META: Record<SocialPlatform, { label: string; Icon: typeof Linkedin }> = {
  linkedin: { label: "LinkedIn", Icon: Linkedin },
  instagram: { label: "Instagram", Icon: Instagram },
  x: { label: "X", Icon: MessageSquare },
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Where the numbers behind a post or insight came from. Synthetic and simulated are deliberately visible. */
export function SourceTag({ sources }: { sources: string[] }) {
  const has = (s: string) => sources.includes(s);
  if (has("synthetic_history"))
    return <span className="rounded-md bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-300 ring-1 ring-amber-400/30">Synthetic demo history</span>;
  if (has("simulated"))
    return <span className="rounded-md bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-300 ring-1 ring-amber-400/30">Simulated</span>;
  if (has("manual")) return <span className="rounded-md bg-raised px-2 py-0.5 text-[11px] font-medium text-body">Your results</span>;
  return <span className="rounded-md bg-raised px-2 py-0.5 text-[11px] font-medium text-muted">No history yet</span>;
}

export const fmtPct = (r: number | null | undefined) => (r == null ? "–" : `${(r * 100).toFixed(1)}%`);

export const fmtIst = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }) + " IST"
    : "";

function Heat({ p }: { p: PlatformInsight }) {
  const max = Math.max(0.0001, ...p.heatmap.flat().map((v) => v ?? 0));
  const parts = p.dayparts ?? [];
  if (!p.heatmap.length) return null;
  return (
    <div className="mt-3 overflow-x-auto">
      <div className="inline-grid gap-[3px]" style={{ gridTemplateColumns: `76px repeat(7, 26px)` }}>
        <span />
        {WEEKDAYS.map((d) => (
          <span key={d} className="text-center text-[10px] text-muted">
            {d[0]}
          </span>
        ))}
        {parts.map((part, pi) => (
          <div key={part} className="contents">
            <span className="pr-2 text-right text-[10px] leading-[22px] text-muted">{part}</span>
            {WEEKDAYS.map((d, di) => {
              const v = p.heatmap[di]?.[pi] ?? null;
              return (
                <span
                  key={d}
                  title={v == null ? `${d} ${part}: no posts` : `${d} ${part}: ${fmtPct(v)} engagement`}
                  className="h-[22px] rounded-[4px]"
                  style={{ background: v == null ? "rgba(255,255,255,0.04)" : `rgba(52,211,153,${0.15 + 0.85 * (v / max)})` }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Best time to post per platform and what the audience responds to, learned from this brand's own posts. */
export function PostingInsightsCard({ brandId, withHeatmap = true }: { brandId: number; withHeatmap?: boolean }) {
  const { data, isLoading } = useQuery({ queryKey: ["posting-insights", brandId], queryFn: () => api.postingInsights(brandId) });
  if (isLoading || !data) return <Card title="Posting intelligence"><Skeleton className="h-40" /></Card>;
  const history = data.basis === "history";
  return (
    <Card title="Posting intelligence" action={<SourceTag sources={data.sources} />}>
      <p className="mb-4 text-sm text-muted">
        {history
          ? `Learned from ${data.posts_analyzed} published posts: when this audience engages and what it responds to.`
          : "No posting history yet, so these are general starting points. Publish a few posts and AdPilot learns your best times."}
      </p>
      <div className="space-y-5">
        {(Object.keys(PLATFORM_META) as SocialPlatform[]).map((k) => {
          const p = data.platforms[k];
          const { label, Icon } = PLATFORM_META[k];
          if (!p) return null;
          return (
            <div key={k}>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <span className="inline-flex w-24 items-center gap-1.5 text-sm text-ink">
                  <Icon className="h-3.5 w-3.5" /> {label}
                </span>
                {p.best_slots.slice(0, 3).map((s, i) => (
                  <span
                    key={i}
                    title={s.confidence}
                    className={cn("rounded-lg px-2.5 py-1 text-xs", i === 0 ? "bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/20" : "bg-surface-2 text-ink/80")}
                  >
                    {s.weekday} {String(s.hour).padStart(2, "0")}:00
                    {s.rate != null && <span className="ml-1.5 text-muted">{fmtPct(s.rate)}</span>}
                  </span>
                ))}
                {p.posts > 0 && <span className="text-xs text-muted">{p.posts} posts · avg {fmtPct(p.avg_rate)}</span>}
              </div>
              {withHeatmap && <Heat p={p} />}
            </div>
          );
        })}
      </div>
      {data.preferences.length > 0 && (
        <div className="mt-6 border-t border-line pt-5">
          <p className="mb-2 text-[13px] font-medium text-muted">What AdPilot has learned</p>
          <ul className="space-y-2">
            {data.preferences.map((t, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-ink/90">
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" /> {t}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/** What is stored in Meko for this brand, and (on request) what it recalls right now. */
export function MemoryCard({ brandId }: { brandId: number }) {
  const [recall, setRecall] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["brand-memory", brandId, recall], queryFn: () => api.brandMemory(brandId, recall), staleTime: 30_000 });
  if (isLoading || !data) return <Card title="Meko memory"><Skeleton className="h-24" /></Card>;
  const on = data.configured && data.status !== "not_configured" && data.status !== "failed";
  const w = data.written;
  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <Brain className="h-4 w-4" /> Meko memory
        </span>
      }
      action={<span className={cn("text-xs", on ? "text-success" : "text-muted")}>{on ? "Connected" : "Not connected"}</span>}
    >
      {on ? (
        <>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {[
              ["Brand facts", w.brand_facts],
              ["Optimization learnings", w.learnings],
              ["Posting patterns", w.posting_patterns],
              ["Agent sessions", w.conversations],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-xl bg-surface-2 px-3 py-2.5">
                <dd className="text-lg tabular-nums text-ink">{v}</dd>
                <dt className="text-xs text-muted">{k}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-muted">
            Every new campaign starts by searching this memory, so the next ads and posts reuse what worked.
            {data.synthetic_history && ` The history here is synthetic demo data (${data.synthetic_history.weeks} weeks, ${data.synthetic_history.campaigns} campaigns, ${data.synthetic_history.posts} posts).`}
          </p>
          {!recall ? (
            <button className="btn-ghost mt-4" onClick={() => setRecall(true)}>
              <Brain className="h-4 w-4" /> Show what Meko recalls
            </button>
          ) : (
            <div className="mt-4 space-y-3">
              {Object.keys(data.recalled).length === 0 && <p className="flex items-center gap-2 text-sm text-muted"><Spinner /> Searching Meko…</p>}
              {Object.entries(data.recalled).map(([q, a]) => (
                <div key={q} className="rounded-xl bg-surface-2 px-4 py-3">
                  <p className="text-xs text-muted">{q}</p>
                  <p className="mt-1.5 line-clamp-6 whitespace-pre-wrap text-xs leading-relaxed text-ink/85">{a.replace(/[{}"\[\]]/g, " ").replace(/\s+/g, " ").slice(0, 700)}</p>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-muted">
          Meko isn't connected, so AdPilot is using its local memory only. Add MEKO_API_KEY to backend/.env to store brand facts, learnings and posting patterns in shared agent memory.
          {data.synthetic_history && " The demo history below is synthetic."}
        </p>
      )}
    </Card>
  );
}
