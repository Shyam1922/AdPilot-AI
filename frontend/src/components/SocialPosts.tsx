import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, RefreshCw, Sparkles, X as XIcon, Image as ImageIcon } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { Card, ModeBadge, RiskFlags, Spinner, StatusPill } from "@/components/ui";
import PublishPanel from "@/components/PublishPanel";
import { PLATFORM_META } from "@/components/PostingInsights";
import type { Language, SocialPlatform, SocialPost } from "@/lib/types";

const PLATFORMS = (Object.keys(PLATFORM_META) as SocialPlatform[]).map((key) => ({ key, ...PLATFORM_META[key] }));

const LANGS: { key: Language; label: string }[] = [
  { key: "en", label: "English" },
  { key: "hinglish", label: "Hinglish" },
  { key: "hi", label: "हिन्दी" },
];

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

/** Draft LinkedIn / Instagram / X posts for one concept, then schedule or publish them. */
export default function SocialPosts({ conceptId, campaignId, brandId }: { conceptId: number; campaignId: number; brandId: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [lang, setLang] = useState<Language>("en");
  const [tab, setTab] = useState<SocialPlatform>("linkedin");

  const { data: all = [] } = useQuery({ queryKey: ["posts", campaignId], queryFn: () => api.listPosts(campaignId) });
  const posts = all.filter((p) => p.concept_id === conceptId);
  const byPlatform = Object.fromEntries(posts.map((p) => [p.platform, p])) as Partial<Record<SocialPlatform, SocialPost>>;
  const current = byPlatform[tab];

  const put = (p: SocialPost) =>
    qc.setQueryData<SocialPost[]>(["posts", campaignId], (d) => (d ?? []).map((x) => (x.id === p.id ? { ...x, ...p, suggested: p.suggested ?? x.suggested } : x)));

  const generate = useMutation({
    mutationFn: () => api.generatePosts(conceptId, { language: lang }),
    onSuccess: (fresh) => {
      qc.setQueryData<SocialPost[]>(["posts", campaignId], (d) => [
        ...(d ?? []).filter((x) => !(x.concept_id === conceptId && fresh.some((f) => f.platform === x.platform))),
        ...fresh,
      ]);
      if (fresh.length) setTab(fresh[0].platform);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Card
      title="Social posts"
      action={
        <div className="flex items-center gap-2">
          <select className="input h-8 py-0 text-xs" value={lang} onChange={(e) => setLang(e.target.value as Language)} aria-label="Post language">
            {LANGS.map((l) => (
              <option key={l.key} value={l.key}>
                {l.label}
              </option>
            ))}
          </select>
          <button className="btn-primary h-8 px-3 text-xs" onClick={() => generate.mutate()} disabled={generate.isPending}>
            {generate.isPending ? <Spinner /> : <Sparkles className="h-3.5 w-3.5" />}
            {posts.length ? "Write again" : "Write posts"}
          </button>
        </div>
      }
    >
      {posts.length === 0 ? (
        <p className="text-sm text-muted">
          One click writes an engaging LinkedIn post, Instagram caption and X post (with a thread) from this concept. It uses only your verified claims, and the timing and style that worked for this brand before. You review, schedule and post them; nothing is posted for you.
        </p>
      ) : (
        <>
          <div className="mb-5 flex gap-1">
            {PLATFORMS.map(({ key, label, Icon }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                disabled={!byPlatform[key]}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition disabled:opacity-40",
                  tab === key ? "bg-white/10 text-ink" : "text-muted hover:text-ink",
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {label}
                {(byPlatform[key]?.status === "approved" || byPlatform[key]?.status === "scheduled" || byPlatform[key]?.status === "published") && (
                  <Check className="h-3 w-3 text-success" />
                )}
              </button>
            ))}
          </div>
          {current && <PostEditor key={current.id} post={current} brandId={brandId} onChange={put} />}
        </>
      )}
    </Card>
  );
}

function PostEditor({ post, brandId, onChange }: { post: SocialPost; brandId: number; onChange: (p: SocialPost) => void }) {
  const toast = useToast();
  const [text, setText] = useState(post.text);
  useEffect(() => setText(post.text), [post.text]);
  const locked = post.status === "published";

  const save = useMutation({
    mutationFn: (patch: { text?: string; status?: "generated" | "approved" | "rejected" }) => api.updatePost(post.id, patch),
    onSuccess: onChange,
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rewrite = useMutation({
    mutationFn: () => api.regeneratePost(post.id),
    onSuccess: onChange,
    onError: (e) => toast.error(errorMessage(e)),
  });

  const copy = async (t: string, what: string) => ((await copyText(t)) ? toast.success(`${what} copied`) : toast.error("Couldn't copy. Select the text and copy it manually."));

  // The server counts links on X as 23 characters; estimate the same while typing.
  const count = post.platform === "x" ? text.replace(/https?:\/\/\S+/g, "x".repeat(23)).length : text.length;
  const over = count > post.char_limit;
  const approved = post.status === "approved" || post.status === "scheduled" || post.status === "published";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-3">
          <ModeBadge mode={post.generation_mode} />
          <StatusPill status={post.status} />
        </span>
        <span className={cn("text-xs tabular-nums", over ? "text-danger" : "text-muted")}>
          {count} / {post.char_limit}
        </span>
      </div>

      <textarea
        className="input min-h-[220px] resize-y whitespace-pre-wrap leading-relaxed"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => !locked && text.trim() && text !== post.text && save.mutate({ text })}
        disabled={rewrite.isPending || locked}
      />

      {post.hashtags.length > 0 && (
        <div>
          <p className="mb-2 text-xs text-muted">
            Top 5 tags for {post.platform === "x" ? "X" : post.platform === "linkedin" ? "LinkedIn" : "Instagram"} · brand, product, niche, community, region · {locked ? "this post is published, click a tag to copy it" : "click to add or remove"}
          </p>
          <div className="flex flex-wrap gap-2">
            {post.hashtags.slice(0, 5).map((tag, i) => {
              const used = new RegExp(`${tag}(?![A-Za-z0-9])`, "i").test(text);
              return (
                <button
                  key={tag}
                  disabled={rewrite.isPending}
                  onClick={() => {
                    if (locked) {
                      void copy(tag, tag);   // published posts can't change, so a click copies the tag
                      return;
                    }
                    const next = used
                      ? text.replace(new RegExp(`\\s*${tag}(?![A-Za-z0-9])`, "i"), "").trimEnd()
                      : `${text.trimEnd()}${/#\w+$/.test(text.trimEnd()) ? " " : "\n\n"}${tag}`;
                    setText(next);
                    if (next.trim()) save.mutate({ text: next });
                  }}
                  className={cn(
                    "rounded-lg px-2.5 py-1 text-xs ring-1 transition disabled:opacity-40",
                    used ? "bg-white text-black ring-transparent" : "bg-transparent text-muted ring-line hover:text-ink hover:ring-white/30",
                  )}
                  title={locked ? "Click to copy this tag" : used ? "In the post. Click to remove." : "Not in the post. Click to add."}
                >
                  <span className="mr-1 opacity-50">{i + 1}</span>{tag}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {post.thread.length > 0 && (
        <div>
          <p className="mb-2 text-xs text-muted">Thread · reply to your first post with these</p>
          <ul className="space-y-2">
            {post.thread.map((t, i) => (
              <li key={i} className="flex items-start justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink/90">
                <span className="whitespace-pre-wrap">{t}</span>
                <button className="shrink-0 text-muted hover:text-ink" onClick={() => copy(t, `Thread ${i + 1}`)} aria-label={`Copy thread post ${i + 1}`}>
                  <Copy className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {post.visual_idea && (
        <p className="flex items-start gap-2 text-xs text-muted">
          <ImageIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {post.visual_idea}
        </p>
      )}

      {post.risk_flags.filter((f) => f.severity !== "info").length > 0 && (
        <div className="border-t border-line pt-4">
          <p className="mb-2 text-[13px] font-medium text-muted">Claim guard</p>
          <RiskFlags flags={post.risk_flags} />
        </div>
      )}

      {!locked && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <button className="btn-ghost" onClick={() => copy(text, "Post")}>
            <Copy className="h-4 w-4" /> Copy
          </button>
          {!approved && (
            <button className="btn-ghost" onClick={() => rewrite.mutate()} disabled={rewrite.isPending}>
              <RefreshCw className={cn("h-4 w-4", rewrite.isPending && "animate-spin")} /> Different take
            </button>
          )}
          <span className="ml-auto flex items-center gap-2">
            {!approved && (
              <button
                className={cn("btn-ghost", post.status === "rejected" && "text-danger ring-1 ring-rose-400/30")}
                onClick={() => save.mutate({ status: post.status === "rejected" ? "generated" : "rejected" })}
                disabled={save.isPending}
              >
                <XIcon className="h-4 w-4" /> {post.status === "rejected" ? "Rejected" : "Reject"}
              </button>
            )}
            <button
              className={cn("btn-primary", approved && "bg-emerald-400 hover:bg-emerald-300")}
              onClick={() => save.mutate({ status: post.status === "approved" ? "generated" : "approved" })}
              disabled={save.isPending || over || post.status === "scheduled"}
              title={over ? "Over the character limit" : post.status === "scheduled" ? "Unschedule to change approval" : undefined}
            >
              {save.isPending ? <Spinner /> : <Check className="h-4 w-4" />} {approved ? "Approved" : "Approve"}
            </button>
          </span>
        </div>
      )}

      {approved && <PublishPanel post={post} brandId={brandId} onChange={onChange} />}
    </div>
  );
}
