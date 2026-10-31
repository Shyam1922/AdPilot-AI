import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Database } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Card, EmptyState, Skeleton, Spinner } from "@/components/ui";
import { fmtIst, fmtPct, PLATFORM_META, SourceTag } from "@/components/PostingInsights";
import type { SocialPlatform, SocialPost } from "@/lib/types";

const AXIS = { fontSize: 11, fill: "#848484" };
const COLORS: Record<SocialPlatform, string> = { linkedin: "#7aa2ff", instagram: "#f08fc0", x: "#e8e8e8" };

/** Monday-start week label for a date. */
function weekStart(iso: string) {
  const d = new Date(iso);
  const day = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
}

/** Weekly engagement per platform: the visible "it's learning" curve. */
function weekly(posts: SocialPost[]) {
  const map = new Map<number, Record<string, { imp: number; eng: number }> & { t: number }>();
  for (const p of posts) {
    const m = p.metrics;
    if (!p.published_at || !m?.impressions) continue;
    const w = weekStart(p.published_at);
    const row = (map.get(w.getTime()) ?? { t: w.getTime() }) as Record<string, any>;
    const cell = (row[p.platform] ??= { imp: 0, eng: 0 });
    cell.imp += m.impressions;
    cell.eng += (m.likes ?? 0) + 2 * (m.comments ?? 0) + 3 * (m.shares ?? 0) + (m.clicks ?? 0);
    map.set(w.getTime(), row as any);
  }
  return [...map.values()]
    .sort((a, b) => a.t - b.t)
    .map((r: any) => ({
      week: new Date(r.t).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
      ...Object.fromEntries((Object.keys(PLATFORM_META) as SocialPlatform[]).map((k) => [k, r[k] ? +((r[k].eng / r[k].imp) * 100).toFixed(2) : null])),
    }));
}

/** Social post results, the learning curve and a table. Works without any ad metrics. */
export default function SocialPerformance({ brandId, campaignId }: { brandId: number; campaignId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: posts, isLoading } = useQuery({ queryKey: ["brand-posts", brandId], queryFn: () => api.brandPosts(brandId) });
  const published = useMemo(() => (posts ?? []).filter((p) => p.status === "published"), [posts]);
  const series = useMemo(() => weekly(published), [published]);
  const mine = (posts ?? []).filter((p) => p.campaign_id === campaignId);
  const mineOpen = mine.filter((p) => p.status === "scheduled" || p.status === "published");

  const sim = useMutation({
    mutationFn: () => api.simulateEngagement(campaignId),
    onSuccess: () => {
      for (const k of ["brand-posts", "posts", "posting-insights", "brand-memory"]) qc.invalidateQueries({ queryKey: [k] });
      toast.success("Simulated engagement loaded (labelled as simulated)");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (isLoading) return <Skeleton className="h-64" />;
  const sources = [...new Set(published.map((p) => p.metrics_source).filter(Boolean))];

  return (
    <Card title="Social performance" action={sources.length ? <SourceTag sources={sources} /> : undefined}>
      {published.length === 0 ? (
        <EmptyState
          icon={<Database className="h-7 w-7" />}
          title="No published posts yet"
          hint="Approve and publish posts from the Creatives tab, then add their results here. Or load clearly labelled simulated engagement to see the learning loop."
          action={
            <button className="btn-ghost" onClick={() => sim.mutate()} disabled={sim.isPending}>
              {sim.isPending ? <Spinner /> : <Database className="h-4 w-4" />} Simulate engagement
            </button>
          }
        />
      ) : (
        <div className="space-y-6">
          <div>
            <p className="mb-1 text-sm text-ink">Engagement rate by week (%)</p>
            <p className="mb-3 text-xs text-muted">Likes + 2×comments + 3×shares + clicks, divided by impressions. Each new campaign uses what the last ones taught it.</p>
            <div className="h-56">
              <ResponsiveContainer>
                <LineChart data={series} margin={{ left: -16, right: 8, top: 8 }}>
                  <CartesianGrid stroke="#1f2023" vertical={false} />
                  <XAxis dataKey="week" tick={AXIS} axisLine={false} tickLine={false} />
                  <YAxis tick={AXIS} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: "#16171a", border: "1px solid #26272b", borderRadius: 12, fontSize: 12 }} />
                  {(Object.keys(PLATFORM_META) as SocialPlatform[]).map((k) => (
                    <Line key={k} type="monotone" dataKey={k} name={PLATFORM_META[k].label} stroke={COLORS[k]} strokeWidth={2} dot={false} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex gap-4 text-xs text-muted">
              {(Object.keys(PLATFORM_META) as SocialPlatform[]).map((k) => (
                <span key={k} className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: COLORS[k] }} /> {PLATFORM_META[k].label}
                </span>
              ))}
            </div>
          </div>

          {mineOpen.length > 0 && (
            <div className="overflow-x-auto">
              <p className="mb-2 text-sm text-ink">This campaign</p>
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted">
                  <tr>
                    <th className="py-2 font-normal">Post</th>
                    <th className="font-normal">When</th>
                    <th className="text-right font-normal">Impr.</th>
                    <th className="text-right font-normal">Engagement</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {mineOpen.map((p) => (
                    <tr key={p.id}>
                      <td className="max-w-[260px] py-2 pr-3">
                        <span className="text-xs text-muted">{PLATFORM_META[p.platform].label}</span>
                        <p className="truncate text-ink/90">{p.hook || p.text}</p>
                      </td>
                      <td className="whitespace-nowrap pr-3 text-xs text-muted">{p.status === "scheduled" ? `Scheduled ${fmtIst(p.scheduled_at)}` : fmtIst(p.published_at)}</td>
                      <td className="text-right tabular-nums">{p.metrics?.impressions ? p.metrics.impressions.toLocaleString("en-IN") : "–"}</td>
                      <td className="text-right tabular-nums text-emerald-300">{fmtPct(p.engagement_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button className="btn-ghost h-9 px-3 text-xs" onClick={() => sim.mutate()} disabled={sim.isPending}>
            {sim.isPending ? <Spinner /> : <Database className="h-3.5 w-3.5" />} Simulate engagement for this campaign's published posts
          </button>
        </div>
      )}
    </Card>
  );
}
