import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Check, Copy, ExternalLink, Send, Sparkles, X as XIcon } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { fmtIst, fmtPct, SourceTag } from "@/components/PostingInsights";
import { Spinner } from "@/components/ui";
import type { PostMetrics, SocialPost } from "@/lib/types";

const enc = encodeURIComponent;
/** Each platform's own "compose" link. We never post for you: you press Post on the platform itself. */
const SHARE: Record<SocialPost["platform"], { label: string; url: (t: string) => string; note: string }> = {
  x: { label: "Post on X", url: (t) => `https://twitter.com/intent/tweet?text=${enc(t)}`, note: "Opens X with the text filled in." },
  linkedin: { label: "Post on LinkedIn", url: (t) => `https://www.linkedin.com/feed/?shareActive=true&text=${enc(t)}`, note: "Opens LinkedIn with the text filled in." },
  instagram: { label: "Open Instagram", url: () => "https://www.instagram.com/", note: "Instagram can't be pre-filled, so the caption is copied: paste it with your video or image." },
};

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}

/** datetime-local wants "YYYY-MM-DDTHH:mm" in the browser's local time. */
const toLocalInput = (iso: string) => {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

/** Schedule or publish an approved post, and record results once it's out. */
export default function PublishPanel({ post, brandId, onChange }: { post: SocialPost; brandId: number; onChange: (p: SocialPost) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [when, setWhen] = useState(() => toLocalInput(post.scheduled_at ?? post.suggested?.at ?? new Date(Date.now() + 3600_000).toISOString()));
  const [opened, setOpened] = useState(false);
  const [link, setLink] = useState("");
  const account = useQuery({ queryKey: ["socials", brandId], queryFn: () => api.listSocials(brandId) }).data?.find((a) => a.platform === post.platform);
  const xLive = useQuery({ queryKey: ["integrations"], queryFn: api.listIntegrations }).data?.find((i) => i.provider === "x_publishing")?.status === "connected" && post.platform === "x";
  const [adding, setAdding] = useState(false);
  const [m, setM] = useState<Record<keyof PostMetrics, string>>({ impressions: "", likes: "", comments: "", shares: "", clicks: "" });

  const done = (p: SocialPost) => {
    onChange(p);
    qc.invalidateQueries({ queryKey: ["posting-insights", brandId] });
    qc.invalidateQueries({ queryKey: ["brand-memory", brandId] });
    qc.invalidateQueries({ queryKey: ["brand-posts", brandId] });
  };
  const onError = (e: unknown) => toast.error(errorMessage(e));

  const schedule = useMutation({ mutationFn: (iso: string) => api.schedulePost(post.id, iso), onSuccess: (p) => { done(p); toast.success("Scheduled"); }, onError });
  const unschedule = useMutation({ mutationFn: () => api.unschedulePost(post.id), onSuccess: done, onError });
  const publish = useMutation({
    mutationFn: (mode: "manual_share" | "simulated" | "api") => api.publishPost(post.id, mode, mode === "manual_share" ? link.trim() : ""),
    onSuccess: (p) => { done(p); setOpened(false); toast.success(p.publish_mode === "simulated" ? "Marked as published (simulated)" : p.publish_mode === "api" ? "Published to X" : "Marked as published"); },
    onError,
  });
  const metrics = useMutation({
    mutationFn: () => api.setPostMetrics(post.id, Object.fromEntries(Object.entries(m).map(([k, v]) => [k, Number(v) || 0]))),
    onSuccess: (p) => { done(p); setAdding(false); toast.success("Results saved. AdPilot learns from them."); },
    onError,
  });

  const share = SHARE[post.platform];
  const openShare = async () => {
    await copyText(post.text);
    window.open(share.url(post.text), "_blank", "noopener,noreferrer");
    setOpened(true);
    toast.info(post.platform === "instagram" ? "Caption copied. Paste it in Instagram." : "Opened with your text. Press Post there, then come back.");
  };

  /* ------------------------------ published ------------------------------ */
  if (post.status === "published") {
    const mm = post.metrics ?? {};
    const hasMetrics = (mm.impressions ?? 0) > 0;
    return (
      <div className="space-y-4 rounded-2xl bg-surface-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="inline-flex items-center gap-2 text-emerald-300">
            <Check className="h-4 w-4" /> Published {fmtIst(post.published_at)}
          </span>
          <span className="text-xs text-muted">
            {post.external_url && <a href={post.external_url} target="_blank" rel="noreferrer" className="mr-3 text-emerald-300 hover:text-white">View post</a>}
            {post.publish_mode === "simulated" ? "Simulated publish (nothing was posted)" : post.publish_mode === "api" ? "Published from AdPilot through the X API" : post.publish_mode === "synthetic_history" ? "Synthetic demo history" : "Posted by you on the platform"}
          </span>
        </div>
        {hasMetrics ? (
          <div>
            <dl className="grid grid-cols-3 gap-2 text-sm sm:grid-cols-6">
              {([["Impressions", mm.impressions], ["Likes", mm.likes], ["Comments", mm.comments], ["Shares", mm.shares], ["Clicks", mm.clicks]] as const).map(([k, v]) => (
                <div key={k}>
                  <dd className="tabular-nums text-ink">{(v ?? 0).toLocaleString("en-IN")}</dd>
                  <dt className="text-xs text-muted">{k}</dt>
                </div>
              ))}
              <div>
                <dd className="tabular-nums text-emerald-300">{fmtPct(post.engagement_rate)}</dd>
                <dt className="text-xs text-muted">Engagement</dt>
              </div>
            </dl>
            <div className="mt-2"><SourceTag sources={[post.metrics_source]} /></div>
          </div>
        ) : adding ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {(Object.keys(m) as (keyof PostMetrics)[]).map((k) => (
                <label key={k} className="text-xs text-muted">
                  <span className="capitalize">{k}</span>
                  <input className="input mt-1 h-9" inputMode="numeric" value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value.replace(/\D/g, "") })} />
                </label>
              ))}
            </div>
            <div className="flex gap-2">
              <button className="btn-primary h-9 px-3 text-xs" onClick={() => metrics.mutate()} disabled={metrics.isPending || !Number(m.impressions)}>
                {metrics.isPending && <Spinner />} Save results
              </button>
              <button className="btn-ghost h-9 px-3 text-xs" onClick={() => setAdding(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <button className="btn-ghost h-9 px-3 text-xs" onClick={() => setAdding(true)}>
            Add results from {post.platform === "x" ? "X" : post.platform === "linkedin" ? "LinkedIn" : "Instagram"}
          </button>
        )}
      </div>
    );
  }

  /* --------------------------- approved / scheduled --------------------------- */
  const scheduled = post.status === "scheduled";
  return (
    <div className="space-y-4 rounded-2xl bg-surface-2 p-4">
      <div className="flex items-center gap-2 text-sm text-ink">
        <Send className="h-4 w-4" /> Publish
        {scheduled && <span className="ml-auto text-xs text-emerald-300">Scheduled for {fmtIst(post.scheduled_at)}</span>}
      </div>

      {post.suggested && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
          <span className="inline-flex items-center gap-1.5 text-emerald-300">
            <Sparkles className="h-3.5 w-3.5" /> Best time: {post.suggested.label}
          </span>
          <span className="text-muted">{post.suggested.reason}</span>
          <button className="underline decoration-dotted underline-offset-2 hover:text-white" onClick={() => setWhen(toLocalInput(post.suggested!.at))}>
            Use it
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input type="datetime-local" className="input h-9 w-auto text-xs" value={when} onChange={(e) => setWhen(e.target.value)} />
        <button className="btn-ghost h-9 px-3 text-xs" disabled={schedule.isPending || !when} onClick={() => schedule.mutate(new Date(when).toISOString())}>
          {schedule.isPending ? <Spinner /> : <CalendarClock className="h-3.5 w-3.5" />} {scheduled ? "Reschedule" : "Schedule"}
        </button>
        {scheduled && (
          <button className="inline-flex items-center gap-1 text-xs text-muted hover:text-white" onClick={() => unschedule.mutate()} disabled={unschedule.isPending}>
            <XIcon className="h-3.5 w-3.5" /> Unschedule
          </button>
        )}
      </div>

      <div className="space-y-2 border-t border-line pt-4">
        <div className="flex flex-wrap items-center gap-2">
          {xLive && (
            <button className="btn-primary h-9 bg-emerald-400 px-3 text-xs hover:bg-emerald-300" onClick={() => publish.mutate("api")} disabled={publish.isPending} title="Posts this to your connected X account right now.">
              {publish.isPending ? <Spinner /> : <Send className="h-3.5 w-3.5" />} Publish to X now
            </button>
          )}
          <button className={cn(xLive ? "btn-ghost" : "btn-primary", "h-9 px-3 text-xs")} onClick={openShare}>
            <ExternalLink className="h-3.5 w-3.5" /> {share.label}
          </button>
          <button className="btn-ghost h-9 px-3 text-xs" onClick={async () => (await copyText(post.text)) && toast.success("Copied")}>
            <Copy className="h-3.5 w-3.5" /> Copy only
          </button>
          {opened && (
            <button className={cn("btn-primary h-9 px-3 text-xs bg-emerald-400 hover:bg-emerald-300")} onClick={() => publish.mutate("manual_share")} disabled={publish.isPending}>
              {publish.isPending ? <Spinner /> : <Check className="h-3.5 w-3.5" />} I posted it
            </button>
          )}
          <button className="ml-auto text-xs text-muted underline decoration-dotted underline-offset-2 hover:text-white" onClick={() => publish.mutate("simulated")} disabled={publish.isPending} title="Records a demo publish. Nothing is posted anywhere.">
            Simulate publish (demo)
          </button>
        </div>
        <p className="text-xs text-muted">
          {account?.connected ? (
            <>Posting as <a href={account.url} target="_blank" rel="noreferrer" className="text-emerald-300 hover:text-white">{account.handle}</a>. </>
          ) : (
            <>No {post.platform === "x" ? "X" : post.platform === "linkedin" ? "LinkedIn" : "Instagram"} account linked yet (Launch tab). </>
          )}
        </p>
        {opened && (
          <input className="input h-9 text-xs" placeholder="Paste the link to your post (optional)" value={link} onChange={(e) => setLink(e.target.value)} />
        )}
        <p className="text-xs text-muted">{share.note} {xLive ? "Publish to X now posts to your connected account only when you press it." : "AdPilot never posts for you; you press Post on the platform."}</p>
      </div>
    </div>
  );
}
