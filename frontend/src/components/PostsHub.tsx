import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { Card, EmptyState, Skeleton, StatusPill } from "@/components/ui";
import PublishPanel from "@/components/PublishPanel";
import { fmtIst, PLATFORM_META } from "@/components/PostingInsights";
import type { SocialPost } from "@/lib/types";

/** Everything approved, scheduled or published for this campaign, with schedule and publish actions. */
export default function PostsHub({ campaignId, brandId, base }: { campaignId: number; brandId: number; base: string }) {
  const { data, isLoading } = useQuery({ queryKey: ["posts", campaignId], queryFn: () => api.listPosts(campaignId) });
  const [open, setOpen] = useState<number | null>(null);
  const [local, setLocal] = useState<Record<number, SocialPost>>({});
  if (isLoading) return <Skeleton className="h-40" />;

  const order = { scheduled: 0, approved: 1, published: 2 } as Record<string, number>;
  const posts = (data ?? [])
    .map((p) => local[p.id] ?? p)
    .filter((p) => ["approved", "scheduled", "published"].includes(p.status))
    .sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9) || (a.scheduled_at ?? "").localeCompare(b.scheduled_at ?? ""));

  return (
    <Card title={`Social posts · ${posts.length}`}>
      {posts.length === 0 ? (
        <EmptyState
          title="No approved posts yet"
          hint="Write and approve LinkedIn, Instagram and X posts in the Creatives tab. They show up here to schedule and publish."
          action={<Link to={`${base}/creatives`} className="btn-ghost">Write posts</Link>}
        />
      ) : (
        <ul className="divide-y divide-line">
          {posts.map((p) => {
            const { Icon, label } = PLATFORM_META[p.platform];
            const isOpen = open === p.id;
            return (
              <li key={p.id} className="py-3 first:pt-0">
                <button className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(isOpen ? null : p.id)}>
                  <Icon className="h-4 w-4 shrink-0 text-muted" aria-label={label} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-ink">{p.hook || p.text}</span>
                    <span className="text-xs text-muted">
                      {p.status === "scheduled" ? `Scheduled ${fmtIst(p.scheduled_at)}` : p.status === "published" ? `Published ${fmtIst(p.published_at)}` : "Ready to schedule"}
                    </span>
                  </span>
                  <StatusPill status={p.status} />
                  <ChevronDown className={cn("h-4 w-4 text-muted transition", isOpen && "rotate-180")} />
                </button>
                {isOpen && (
                  <div className="mt-3 space-y-3">
                    <p className="whitespace-pre-wrap rounded-xl bg-surface-2 p-3 text-sm leading-relaxed text-ink/90">{p.text}</p>
                    <PublishPanel post={p} brandId={brandId} onChange={(np) => setLocal((l) => ({ ...l, [np.id]: { ...np, suggested: np.suggested ?? p.suggested } }))} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
