import { useRef } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ArrowRight, Database, GitBranch, Sparkles, Upload } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn, inr, mult, num, pct } from "@/lib/format";
import { useToast } from "@/components/toast";
import { Card, EmptyState, ErrorState, ModeBadge, Skeleton, SourceBadge, Spinner } from "@/components/ui";
import type { Analytics, Iteration, SampleStatus } from "@/lib/types";
import SocialPerformance from "@/components/SocialPerformance";
import { MemoryCard, PostingInsightsCard } from "@/components/PostingInsights";
import { useCampaign } from "../Campaign";

const SAMPLE: Record<SampleStatus, { label: string; color: string }> = {
  insufficient_data: { label: "Insufficient data", color: "#3a3b40" },
  early_signal: { label: "Early signal", color: "#8a8b90" },
  directional: { label: "Directional", color: "#f5f5f5" },
};

const AXIS = { fontSize: 11, fill: "#848484" };
const GRID = "#1f2023";
const TOOLTIP = {
  contentStyle: { background: "#16171a", border: "1px solid #26272b", borderRadius: 12, color: "#ededed", fontSize: 12 },
  labelStyle: { color: "#848484" },
  cursor: { fill: "rgba(255,255,255,0.03)" },
};

export default function Performance() {
  const { detail } = useCampaign();
  const id = detail.campaign.id;
  const analytics = useQuery({ queryKey: ["analytics", id], queryFn: () => api.getAnalytics(id), enabled: detail.has_metrics });

  const brandId = detail.campaign.brand_id;
  return (
    <div className="space-y-6">
      <SocialPerformance brandId={brandId} campaignId={id} />
      <div className="grid gap-6 lg:grid-cols-2">
        <PostingInsightsCard brandId={brandId} />
        <MemoryCard brandId={brandId} />
      </div>
      <h2 className="display pt-2 text-xl">Ad performance</h2>
      {!detail.has_metrics ? (
        <EmptyState
          icon={<Database className="h-7 w-7" />}
          title="No ad results yet"
          hint="Import results from your ad accounts as CSV, or load clearly labelled simulated data to try the optimization loop."
          action={<DataActions campaignId={id} primary />}
        />
      ) : analytics.isLoading ? (
        <Skeleton className="h-96" />
      ) : analytics.error || !analytics.data ? (
        <ErrorState error={analytics.error} onRetry={() => analytics.refetch()} />
      ) : (
        <>
          <Overview a={analytics.data} />
          <Optimization iterations={detail.iterations} campaignId={id} />
        </>
      )}
    </div>
  );
}

function DataActions({ campaignId, primary }: { campaignId: number; primary?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["campaign", campaignId] });
    qc.invalidateQueries({ queryKey: ["analytics", campaignId] });
  };

  const simulate = useMutation({
    mutationFn: () => api.simulateMetrics(campaignId, { days: 7 }),
    onSuccess: (r) => {
      refresh();
      toast.success(`${r.rows_saved} simulated rows loaded`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const importCsv = useMutation({
    mutationFn: (f: File) => api.importMetrics(campaignId, f),
    onSuccess: (r) => {
      refresh();
      if (r.errors.length) toast.error(`${r.rows_saved} rows imported, ${r.errors.length} skipped: ${r.errors[0]}`);
      else toast.success(`${r.rows_saved} rows imported`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className={cn("flex items-center gap-2", primary && "flex-col")}>
      <div className="flex items-center gap-2">
        <button className={primary ? "btn-primary" : "btn-ghost"} onClick={() => file.current?.click()} disabled={importCsv.isPending}>
          {importCsv.isPending ? <Spinner /> : <Upload className="h-4 w-4" />} Import CSV
        </button>
        <button className="btn-ghost" onClick={() => simulate.mutate()} disabled={simulate.isPending}>
          {simulate.isPending ? <Spinner /> : <Database className="h-4 w-4" />} {primary ? "Use simulated data" : "Re-simulate"}
        </button>
      </div>
      {primary && <p className="mt-2 font-mono text-[11px] text-muted">concept_id, day, platform, impressions, clicks, conversions, spend, revenue</p>}
      <input
        ref={file}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) importCsv.mutate(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function Overview({ a }: { a: Analytics }) {
  const { detail } = useCampaign();
  const metric = a.objective_metric;
  const fmt = (v: number | null) => (metric === "roas" ? mult(v) : pct(v));
  const t = a.totals;

  const bars = a.by_concept.map((c) => ({
    name: c.label,
    value: c.primary_value ?? 0,
    err:
      c.primary_value != null && c.ci_low != null && c.ci_high != null
        ? [c.primary_value - c.ci_low, c.ci_high - c.primary_value]
        : [0, 0],
    color: SAMPLE[c.sample_status].color,
  }));

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-muted">
          Data source {a.data_sources.map((s) => <SourceBadge key={s} source={s} />)}
        </div>
        <DataActions campaignId={detail.campaign.id} />
      </div>

      {a.is_simulated && (
        <div className="flex items-center gap-3 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-5 py-3 text-sm text-amber-100">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />
          These numbers are simulated to exercise the loop. They are not real ad performance.
        </div>
      )}

      <div className="grid grid-cols-2 overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4 [&>*]:bg-surface" style={{ gap: 1 }}>
        <Kpi label="Impressions" value={num(t.impressions)} />
        <Kpi label="Clicks" value={num(t.clicks)} />
        <Kpi label="CTR" value={pct(t.ctr)} sub={`${num(t.clicks)} / ${num(t.impressions)}`} highlight={metric === "ctr"} />
        <Kpi label="Conversions" value={num(t.conversions)} />
        <Kpi label="CVR" value={pct(t.cvr)} sub={`${num(t.conversions)} / ${num(t.clicks)}`} highlight={metric === "cvr"} />
        <Kpi label="Spend" value={inr(t.spend)} />
        <Kpi label="CPA" value={inr(t.cpa)} />
        <Kpi label="ROAS" value={mult(t.roas)} sub={t.revenue != null ? `${inr(t.revenue)} revenue` : undefined} highlight={metric === "roas"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`${metric.toUpperCase()} by concept · 95% interval`}>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bars} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} interval={0} tickFormatter={(s: string) => (s.length > 14 ? `${s.slice(0, 13)}…` : s)} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => (metric === "roas" ? `${v}×` : `${(v * 100).toFixed(1)}%`)} />
                <Tooltip {...TOOLTIP} formatter={(v: number) => [fmt(v), metric.toUpperCase()]} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false}>
                  {bars.map((b, i) => (
                    <Cell key={i} fill={b.color} />
                  ))}
                  <ErrorBar dataKey="err" width={6} strokeWidth={1.5} stroke="#ffffff" direction="y" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex gap-4 text-xs text-muted">
            {Object.values(SAMPLE).map((s) => (
              <span key={s.label} className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-sm" style={{ background: s.color }} /> {s.label}
              </span>
            ))}
          </div>
        </Card>

        <Card title="Daily clicks and conversions">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={a.daily} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={(d: string) => d.slice(5)} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} />
                <Tooltip {...TOOLTIP} />
                <Line type="monotone" dataKey="clicks" stroke="#f5f5f5" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="conversions" stroke="#8a8b90" strokeWidth={2} strokeDasharray="4 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 flex gap-4 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-3 bg-[#f5f5f5]" /> Clicks</span>
            <span className="inline-flex items-center gap-1.5"><span className="w-3 border-t-2 border-dashed border-[#8a8b90]" /> Conversions</span>
          </div>
        </Card>
      </div>

      <Card title="By concept">
        <div className="-mx-6 overflow-x-auto px-6">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="pb-3 font-medium">Concept</th>
              <th className="pb-3 text-right font-medium">Impr.</th>
              <th className="pb-3 text-right font-medium">Clicks</th>
              <th className="pb-3 text-right font-medium">Conv.</th>
              <th className="pb-3 text-right font-medium">{metric.toUpperCase()}</th>
              <th className="pb-3 text-right font-medium">95% interval</th>
              <th className="pb-3 text-right font-medium">P(best)</th>
              <th className="pb-3 pl-6 font-medium">Sample</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {a.by_concept.map((c) => (
              <tr key={c.concept_id}>
                <td className="py-3">
                  <p className="text-ink">{c.label}</p>
                  <p className="text-xs capitalize text-muted">
                    {c.concept_type}
                    {c.is_exploration && " · exploration"}
                  </p>
                </td>
                <td className="py-3 text-right tabular-nums text-ink/80">{num(c.impressions)}</td>
                <td className="py-3 text-right tabular-nums text-ink/80">{num(c.clicks)}</td>
                <td className="py-3 text-right tabular-nums text-ink/80">{num(c.conversions)}</td>
                <td className="py-3 text-right font-medium tabular-nums text-ink">{fmt(c.primary_value)}</td>
                <td className="py-3 text-right text-xs tabular-nums text-muted">{c.ci_low != null ? `${fmt(c.ci_low)} – ${fmt(c.ci_high)}` : "—"}</td>
                <td className="py-3 text-right tabular-nums text-ink/80">{pct(c.p_best, 0)}</td>
                <td className="py-3 pl-6">
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                    <span className="h-2 w-2 rounded-sm" style={{ background: SAMPLE[c.sample_status].color }} />
                    {SAMPLE[c.sample_status].label}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {a.objective_metric_note && <p className="mt-4 text-xs text-muted">{a.objective_metric_note}</p>}
      </Card>

      {a.warnings.length > 0 && (
        <ul className="space-y-1.5 text-sm text-amber-100/80">
          {a.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" /> {w}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Kpi({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div className="px-5 py-4">
      <p className={cn("text-xs", highlight ? "text-white" : "text-muted")}>
        {label}
        {highlight && " · objective"}
      </p>
      <p className="mt-2 font-serif text-[28px] font-light leading-none tabular-nums text-white">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] tabular-nums text-muted">{sub}</p>}
    </div>
  );
}

function Optimization({ iterations, campaignId }: { iterations: Iteration[]; campaignId: number }) {
  const { detail } = useCampaign();
  const qc = useQueryClient();
  const toast = useToast();
  const iterate = useMutation({
    mutationFn: () => api.iterate(campaignId, { batch_size: 4 }),
    onSuccess: (it) => {
      qc.invalidateQueries({ queryKey: ["campaign", campaignId] });
      qc.invalidateQueries({ queryKey: ["brand", detail.campaign.brand_id] });
      toast.success(`${it.variants.length} new variants drafted`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <section className="space-y-4 pt-4">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div>
          <h2 className="display text-[32px] leading-tight">Optimization</h2>
          <p className="mt-2 text-[15px] text-muted">Ranks concepts on the numbers above, explains why, and drafts the next variants. Learnings go back to Brand Memory.</p>
        </div>
        <button className="btn-primary shrink-0" onClick={() => iterate.mutate()} disabled={iterate.isPending}>
          {iterate.isPending ? <Spinner /> : <Sparkles className="h-4 w-4" />} {iterate.isPending ? "Analyzing…" : "Run optimization"}
        </button>
      </div>
      {[...iterations].reverse().map((it, i) => (
        <IterationCard key={it.id} it={it} round={iterations.length - i} />
      ))}
    </section>
  );
}

function IterationCard({ it, round }: { it: Iteration; round: number }) {
  const { base } = useCampaign();
  return (
    <div className="card p-6">
      <div className="mb-4 flex items-center gap-3">
        <span className="text-[15px] font-medium text-white">Round {round}</span>
        <ModeBadge mode={it.generation_mode} />
        {it.data_sources.map((s) => (
          <SourceBadge key={s} source={s} />
        ))}
      </div>
      <p className="leading-relaxed text-ink/90">{it.insight_summary}</p>

      <div className="mt-6 grid gap-8 md:grid-cols-2">
        <div>
          <p className="mb-2 text-[13px] font-medium text-muted">Signals used</p>
          <ul className="space-y-1.5 text-sm text-ink/80">
            {it.selected_signals.map((s, i) => (
              <li key={i}>
                <span className="text-muted">#{s.concept_id}</span> {s.signal}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-2 text-[13px] font-medium text-amber-300/80">Limitations</p>
          <ul className="space-y-1.5 text-sm text-ink/80">
            {it.limitations.map((l, i) => (
              <li key={i}>· {l}</li>
            ))}
          </ul>
        </div>
      </div>

      {it.variants.length > 0 && (
        <div className="mt-6 border-t border-line pt-5">
          <p className="mb-3 text-[13px] font-medium text-muted">Next variants</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {it.variants.map((v) => (
              <Link
                key={v.id}
                to={`${base}/creatives?c=${v.id}`}
                className="group rounded-xl bg-surface-2 p-4 ring-1 ring-transparent transition hover:ring-white/20"
              >
                <p className="flex items-center gap-1.5 text-xs text-muted">
                  {v.is_exploration ? (
                    <span className="text-white">Exploration</span>
                  ) : (
                    <>
                      <GitBranch className="h-3 w-3" /> #{v.parent_concept_id} · {v.changed_variables.join(", ")}
                    </>
                  )}
                </p>
                <p className="mt-1.5 text-sm text-ink">{v.hook}</p>
                <p className="mt-1 line-clamp-2 text-xs text-muted">{v.rationale}</p>
                <p className="mt-2 inline-flex items-center gap-1 text-xs text-white opacity-0 transition group-hover:opacity-100">
                  Open <ArrowRight className="h-3 w-3" />
                </p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
