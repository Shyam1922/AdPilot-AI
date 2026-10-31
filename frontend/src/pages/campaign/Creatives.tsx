import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronDown, Download, Film, GitBranch, Play, RefreshCw, X } from "lucide-react";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { Card, EmptyState, ModeBadge, RiskFlags, Spinner, StatusPill } from "@/components/ui";
import GenerateConcepts from "@/components/GenerateConcepts";
import type { Asset, CampaignDetail, Concept, CopyField } from "@/lib/types";
import { useCampaign } from "../Campaign";

const TYPE_LABEL: Record<string, string> = {
  problem: "Problem",
  demo: "Demo",
  storytelling: "Storytelling",
  offer: "Offer",
  "testimonial-style": "Testimonial-style",
};

/** Put a server-returned concept into the cached campaign detail (no refetch, no input flicker). */
function replaceConcept(qc: QueryClient, campaignId: number, concept: Concept) {
  qc.setQueryData<CampaignDetail>(["campaign", campaignId], (d) =>
    d ? { ...d, concepts: d.concepts.map((c) => (c.id === concept.id ? concept : c)) } : d,
  );
}

export default function Creatives() {
  const { detail } = useCampaign();
  const [params, setParams] = useSearchParams();
  const concepts = detail.concepts;

  if (concepts.length === 0) {
    return (
      <EmptyState
        title="No creatives yet"
        hint="Generate five concepts from the strategy: one per angle, each with platform copy and a video script."
        action={<GenerateConcepts campaignId={detail.campaign.id} />}
      />
    );
  }

  const selected = concepts.find((c) => c.id === Number(params.get("c"))) ?? concepts[0];
  const select = (id: number) => setParams({ c: String(id) }, { replace: true });

  const groups: { label: string; items: Concept[] }[] = [{ label: "Concepts", items: concepts.filter((c) => c.iteration_id == null) }];
  detail.iterations.forEach((it, i) => {
    const items = concepts.filter((c) => c.iteration_id === it.id);
    if (items.length) groups.push({ label: `Optimization round ${i + 1}`, items });
  });

  return (
    <div className="grid grid-cols-[300px_minmax(0,1fr)] gap-8">
      <aside className="space-y-6">
        {groups.map((g) => (
          <div key={g.label}>
            <p className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-muted">{g.label}</p>
            <div className="space-y-1.5">
              {g.items.map((c) => (
                <ConceptRow key={c.id} concept={c} active={c.id === selected.id} onClick={() => select(c.id)} />
              ))}
            </div>
          </div>
        ))}
        <GenerateConcepts campaignId={detail.campaign.id} label="Generate 5 more" ghost />
      </aside>

      <ConceptDetail key={selected.id} concept={selected} campaignId={detail.campaign.id} />
    </div>
  );
}

function ConceptRow({ concept, active, onClick }: { concept: Concept; active: boolean; onClick: () => void }) {
  const blocking = concept.risk_flags.filter((f) => f.severity !== "info").length;
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-lg px-3.5 py-3 text-left transition",
        active ? "bg-brand-500/15 ring-1 ring-brand-500/40" : "hover:bg-white/5",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted">
          {TYPE_LABEL[concept.concept_type] ?? concept.concept_type}
          {concept.is_exploration && " · exploration"}
        </span>
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            concept.status === "approved" ? "bg-success" : concept.status === "rejected" ? "bg-danger" : "bg-white/20",
          )}
          title={concept.status}
        />
      </div>
      <p className={cn("mt-1 line-clamp-2 text-sm", active ? "text-ink" : "text-ink/80")}>{concept.hook || "Untitled"}</p>
      {(blocking > 0 || concept.latest_video?.status === "ready") && (
        <div className="mt-1.5 flex items-center gap-3 text-[11px]">
          {blocking > 0 && (
            <span className="inline-flex items-center gap-1 text-amber-300">
              <AlertTriangle className="h-3 w-3" /> {blocking}
            </span>
          )}
          {concept.latest_video?.status === "ready" && (
            <span className="inline-flex items-center gap-1 text-muted">
              <Film className="h-3 w-3" /> video
            </span>
          )}
        </div>
      )}
    </button>
  );
}

function ConceptDetail({ concept, campaignId }: { concept: Concept; campaignId: number }) {
  const qc = useQueryClient();
  const toast = useToast();

  const save = useMutation({
    mutationFn: (patch: Partial<Record<CopyField, string>>) => api.updateConcept(concept.id, patch),
    onSuccess: (c) => replaceConcept(qc, campaignId, c),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const regenerate = useMutation({
    mutationFn: (field: CopyField) => api.regenerateField(concept.id, field),
    onSuccess: (c) => replaceConcept(qc, campaignId, c),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const setStatus = useMutation({
    mutationFn: (status: "approved" | "rejected" | "generated") => api.updateConcept(concept.id, { status }),
    onSuccess: (c) => {
      replaceConcept(qc, campaignId, c);
      qc.invalidateQueries({ queryKey: ["campaign", campaignId] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const field = (key: CopyField, label: string, opts: { multiline?: boolean; max?: number } = {}) => (
    <CopyInput
      label={label}
      value={concept[key]}
      multiline={opts.multiline}
      max={opts.max}
      saving={save.isPending && key in (save.variables ?? {})}
      regenerating={regenerate.isPending && regenerate.variables === key}
      onSave={(v) => save.mutate({ [key]: v })}
      onRegenerate={() => regenerate.mutate(key)}
    />
  );

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-ink">
              {TYPE_LABEL[concept.concept_type] ?? concept.concept_type} <span className="font-normal text-muted">#{concept.id}</span>
            </h2>
            <StatusPill status={concept.status} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {concept.target_segment}
            {concept.angle && <> · {concept.angle}</>}
          </p>
          <div className="mt-2 flex items-center gap-3">
            <ModeBadge mode={concept.generation_mode} />
            {concept.edited && <span className="text-xs text-muted">· edited</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            className={cn("btn-ghost", concept.status === "rejected" && "text-danger ring-1 ring-rose-400/30")}
            onClick={() => setStatus.mutate(concept.status === "rejected" ? "generated" : "rejected")}
            disabled={setStatus.isPending}
          >
            <X className="h-4 w-4" /> {concept.status === "rejected" ? "Rejected" : "Reject"}
          </button>
          <button
            className={cn("btn-primary", concept.status === "approved" && "bg-emerald-600 hover:bg-emerald-700")}
            onClick={() => setStatus.mutate(concept.status === "approved" ? "generated" : "approved")}
            disabled={setStatus.isPending}
          >
            {setStatus.isPending ? <Spinner /> : <Check className="h-4 w-4" />} {concept.status === "approved" ? "Approved" : "Approve"}
          </button>
        </div>
      </div>

      {(concept.parent_concept_id || concept.rationale) && (
        <div className="rounded-xl bg-white/[0.03] px-5 py-4 text-sm ring-1 ring-white/5">
          {concept.parent_concept_id && (
            <p className="flex items-center gap-2 text-brand-300">
              <GitBranch className="h-4 w-4" /> Variant of #{concept.parent_concept_id}
              {concept.changed_variables.length > 0 && <span className="text-muted">· changed {concept.changed_variables.join(", ")}</span>}
            </p>
          )}
          {concept.rationale && <p className={cn("text-ink/80", concept.parent_concept_id && "mt-1.5")}>{concept.rationale}</p>}
        </div>
      )}

      <Card title="Copy">
        <div className="space-y-5">
          {field("hook", "Hook")}
          {field("primary_text", "Primary text", { multiline: true })}
          <div className="grid grid-cols-2 gap-5">
            {field("headline", "Headline", { max: 40 })}
            {field("cta", "Call to action", { max: 20 })}
          </div>
        </div>
        {concept.risk_flags.length > 0 && (
          <div className="mt-6 border-t border-line pt-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Claim guard</p>
            <RiskFlags flags={concept.risk_flags} />
          </div>
        )}
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)_280px] gap-6">
        <PlatformCopy concept={concept} />
        <VideoPanel concept={concept} campaignId={campaignId} />
      </div>

      <VisualBrief concept={concept} />
    </div>
  );
}

function CopyInput({
  label,
  value,
  multiline,
  max,
  saving,
  regenerating,
  onSave,
  onRegenerate,
}: {
  label: string;
  value: string;
  multiline?: boolean;
  max?: number;
  saving: boolean;
  regenerating: boolean;
  onSave: (v: string) => void;
  onRegenerate: () => void;
}) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const commit = () => {
    if (v.trim() && v !== value) onSave(v);
  };
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="label mb-0">{label}</span>
        <span className="flex items-center gap-3 text-xs">
          {saving && <span className="text-muted">Saving…</span>}
          {max && <span className={cn(v.length > max ? "text-warn" : "text-muted")}>{v.length}/{max}</span>}
          <button onClick={onRegenerate} disabled={regenerating} className="inline-flex items-center gap-1 text-muted hover:text-brand-300 disabled:opacity-50">
            <RefreshCw className={cn("h-3 w-3", regenerating && "animate-spin")} /> Rewrite
          </button>
        </span>
      </div>
      {multiline ? (
        <textarea className="input min-h-[88px] resize-y leading-relaxed" value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} disabled={regenerating} />
      ) : (
        <input
          className="input"
          value={v}
          onChange={(e) => setV(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          disabled={regenerating}
        />
      )}
    </div>
  );
}

function PlatformCopy({ concept }: { concept: Concept }) {
  const pc = concept.platform_copy;
  const tabs = [
    pc.instagram && { key: "instagram", label: "Instagram" },
    pc.meta_ads && { key: "meta_ads", label: "Meta Ads" },
    pc.google_ads && { key: "google_ads", label: "Google Ads" },
  ].filter(Boolean) as { key: string; label: string }[];
  const [tab, setTab] = useState(tabs[0]?.key);
  const active = tabs.find((t) => t.key === tab)?.key ?? tabs[0]?.key;

  return (
    <Card title="Platform copy">
      {tabs.length === 0 ? (
        <p className="text-sm text-muted">No platform copy for this concept.</p>
      ) : (
        <>
          <div className="mb-5 flex gap-1">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={cn("rounded-md px-3 py-1.5 text-sm transition", active === t.key ? "bg-white/10 text-ink" : "text-muted hover:text-ink")}
              >
                {t.label}
              </button>
            ))}
          </div>

          {active === "instagram" && pc.instagram && (
            <div className="space-y-3">
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink/90">{pc.instagram.caption}</p>
              <p className="text-sm text-brand-300">{pc.instagram.hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)).join(" ")}</p>
            </div>
          )}

          {active === "meta_ads" && pc.meta_ads && (
            <dl className="space-y-3 text-sm">
              <Row k="Primary text" v={pc.meta_ads.primary_text} />
              <Row k="Headline" v={pc.meta_ads.headline} />
              <Row k="Description" v={pc.meta_ads.description} />
              <Row k="Button" v={pc.meta_ads.cta} />
            </dl>
          )}

          {active === "google_ads" && pc.google_ads && (
            <div className="space-y-5 text-sm">
              <Limited title="Headlines" items={pc.google_ads.headlines} max={30} />
              <Limited title="Descriptions" items={pc.google_ads.descriptions} max={90} />
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="text-ink/90">{v}</dd>
    </div>
  );
}

function Limited({ title, items, max }: { title: string; items: string[]; max: number }) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted">
        {title} · max {max} characters
      </p>
      <ul className="space-y-1.5">
        {items.map((t, i) => (
          <li key={i} className="flex items-center justify-between gap-3 rounded-md bg-white/[0.03] px-3 py-2">
            <span className="truncate text-ink/90">{t}</span>
            <span className={cn("shrink-0 text-xs tabular-nums", t.length > max ? "text-danger" : "text-muted")}>{t.length}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function VideoPanel({ concept, campaignId }: { concept: Concept; campaignId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const latest = concept.latest_video;
  const [assetId, setAssetId] = useState<number | null>(latest?.id ?? null);
  useEffect(() => setAssetId(latest?.id ?? null), [latest?.id]);

  const { data: health } = useQuery({ queryKey: ["health"], queryFn: api.health });

  const render = useMutation({
    mutationFn: () => api.renderVideo(concept.id, { format: "9:16" }),
    onSuccess: (a) => {
      qc.setQueryData(["asset", a.id], a);
      setAssetId(a.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const { data: asset } = useQuery({
    queryKey: ["asset", assetId],
    queryFn: () => api.getAsset(assetId!),
    enabled: assetId != null,
    initialData: latest && latest.id === assetId ? latest : undefined,
    refetchInterval: (q) => {
      const s = (q.state.data as Asset | undefined)?.status;
      return s === "ready" || s === "failed" ? false : 1500;
    },
  });

  // When a render finishes, refresh the campaign so lists and counts pick up the video.
  useEffect(() => {
    if (asset && (asset.status === "ready" || asset.status === "failed") && asset.id !== latest?.id) {
      qc.invalidateQueries({ queryKey: ["campaign", campaignId] });
    }
  }, [asset, latest?.id, campaignId, qc]);

  const busy = asset?.status === "queued" || asset?.status === "rendering";

  return (
    <Card title="Video ad" action={asset?.status === "ready" ? <ModeBadge mode={asset.generation_mode} /> : undefined}>
      {asset?.status === "ready" && asset.url ? (
        <div className="space-y-3">
          <video src={fileUrl(asset.url)} controls playsInline className="aspect-[9/16] w-full rounded-lg bg-black" />
          <div className="flex items-center justify-between text-xs text-muted">
            <span>
              {asset.meta.duration_s ? `${asset.meta.duration_s}s · ` : ""}
              {asset.meta.width}×{asset.meta.height}
            </span>
            <span className="flex items-center gap-3">
              <a href={fileUrl(asset.url)} download className="inline-flex items-center gap-1 hover:text-ink">
                <Download className="h-3.5 w-3.5" /> MP4
              </a>
              <button onClick={() => render.mutate()} disabled={render.isPending} className="inline-flex items-center gap-1 hover:text-ink">
                <RefreshCw className="h-3.5 w-3.5" /> Re-render
              </button>
            </span>
          </div>
        </div>
      ) : busy && asset ? (
        <div className="flex aspect-[9/16] flex-col items-center justify-center rounded-lg bg-black/20 px-6 ring-1 ring-white/5">
          <Spinner className="h-5 w-5 text-brand-400" />
          <p className="mt-3 text-sm text-ink">{asset.status === "queued" ? "Queued" : "Rendering"}</p>
          <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${Math.max(4, asset.progress * 100)}%` }} />
          </div>
          <p className="mt-2 text-xs text-muted">{Math.round(asset.progress * 100)}% · keep working meanwhile</p>
        </div>
      ) : (
        <div className="flex aspect-[9/16] flex-col items-center justify-center rounded-lg bg-black/20 px-6 text-center ring-1 ring-white/5">
          {asset?.status === "failed" && <p className="mb-3 text-sm text-rose-300">Render failed{asset.error ? `: ${asset.error}` : ""}</p>}
          <p className="text-sm text-muted">15-second 9:16 reel from this script, with the real product image composited in.</p>
          {health && !health.ffmpeg && <p className="mt-2 text-xs text-warn">FFmpeg is missing on the server.</p>}
          <button className="btn-primary mt-5" onClick={() => render.mutate()} disabled={render.isPending}>
            {render.isPending ? <Spinner /> : <Play className="h-4 w-4" />}
            {asset?.status === "failed" ? "Retry" : "Render video"}
          </button>
        </div>
      )}

      {concept.video_script.length > 0 && (
        <ol className="mt-5 space-y-3 border-t border-line pt-5">
          {concept.video_script.map((b, i) => (
            <li key={i} className="text-sm">
              <p className="text-xs text-muted">
                <span className="capitalize text-brand-300">{b.beat}</span> · {b.seconds}s
              </p>
              <p className="text-ink/90">{b.on_screen_text}</p>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function VisualBrief({ concept }: { concept: Concept }) {
  const [open, setOpen] = useState(false);
  const b = concept.visual_brief;
  if (!b) return null;
  const rows: [string, string][] = [
    ["Scene", b.scene],
    ["Composition", b.composition],
    ["Product placement", b.product_placement],
    ["Text-safe area", b.text_safe_area],
    ["Style", b.style],
    ["Layout", b.layout],
  ];
  return (
    <section className="card">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-6 py-4 text-left">
        <span className="text-[13px] font-semibold uppercase tracking-wider text-muted">Visual brief</span>
        <ChevronDown className={cn("h-4 w-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && (
        <dl className="space-y-2.5 px-6 pb-6 text-sm">
          {rows.filter(([, v]) => v).map(([k, v]) => (
            <div key={k} className="grid grid-cols-[150px_1fr] gap-3">
              <dt className="text-muted">{k}</dt>
              <dd className="text-ink/90">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
