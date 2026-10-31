import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { ErrorState, Skeleton, StatusPill } from "@/components/ui";
import type { CampaignDetail } from "@/lib/types";
import { channelLabel } from "./Campaigns";

// The campaign workspace is the ecosystem loop: Strategist → Creative Studio → Campaign Manager → Analytics/Optimization.
const STEPS = [
  { to: "strategy", label: "Strategy" },
  { to: "creatives", label: "Creatives" },
  { to: "launch", label: "Launch" },
  { to: "performance", label: "Performance" },
];

export interface CampaignCtx {
  detail: CampaignDetail;
  brandId: number;
  base: string;
}

export function useCampaign() {
  return useOutletContext<CampaignCtx>();
}

export default function Campaign() {
  const { brandId, campaignId } = useParams();
  const id = Number(campaignId);
  const base = `/brands/${brandId}/campaigns/${id}`;
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["campaign", id], queryFn: () => api.getCampaign(id) });

  if (isLoading)
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-96" />
        <Skeleton className="h-10" />
        <Skeleton className="h-72" />
      </div>
    );
  if (error || !data) return <ErrorState error={error} onRetry={() => refetch()} />;

  const c = data.campaign;
  const done = {
    strategy: true,
    creatives: data.concepts.length > 0,
    launch: c.status === "approved" || c.status === "scheduled" || c.status === "published",
    performance: data.has_metrics,
  } as Record<string, boolean>;

  return (
    <div>
      <Link to={`/brands/${brandId}/campaigns`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Campaigns
      </Link>

      <div className="mb-8 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="truncate font-serif text-[28px] font-semibold leading-tight text-ink">{c.name}</h1>
          <p className="mt-1.5 text-sm text-muted">
            <span className="capitalize">{c.objective}</span> · {c.channels.map(channelLabel).join(", ")}
            {c.product_focus && <> · {c.product_focus}</>}
          </p>
        </div>
        <StatusPill status={c.status} />
      </div>

      <nav className="mb-8 flex gap-1 border-b border-line">
        {STEPS.map((s, i) => (
          <NavLink
            key={s.to}
            to={`${base}/${s.to}`}
            className={({ isActive }) =>
              cn(
                "-mb-px flex items-center gap-2.5 border-b-2 px-4 py-3 text-sm transition",
                isActive ? "border-brand-500 text-ink" : "border-transparent text-muted hover:text-ink",
              )
            }
          >
            <span
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
                done[s.to] ? "bg-brand-500/20 text-brand-300" : "bg-white/5 text-muted",
              )}
            >
              {i + 1}
            </span>
            {s.label}
          </NavLink>
        ))}
      </nav>

      <Outlet context={{ detail: data, brandId: Number(brandId), base } satisfies CampaignCtx} />
    </div>
  );
}
