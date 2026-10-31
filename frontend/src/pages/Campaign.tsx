import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check } from "lucide-react";
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
      <Link to={`/brands/${brandId}/campaigns`} className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-white">
        <ArrowLeft className="h-4 w-4" /> Campaigns
      </Link>

      <div className="mb-10 flex items-end justify-between gap-6">
        <div className="min-w-0">
          <h1 className="display truncate text-[40px] leading-[1.1]">{c.name}</h1>
          <p className="mt-3 text-[15px] text-muted">
            <span className="capitalize">{c.objective}</span> · {c.channels.map(channelLabel).join(", ")}
            {c.product_focus && <> · {c.product_focus}</>}
          </p>
        </div>
        <StatusPill status={c.status} />
      </div>

      <nav className="mb-10 grid grid-cols-4 gap-6">
        {STEPS.map((s, i) => (
          <NavLink
            key={s.to}
            to={`${base}/${s.to}`}
            className={({ isActive }) =>
              cn("group border-t pt-4 transition", isActive ? "border-white" : "border-line hover:border-white/40")
            }
          >
            {({ isActive }) => (
              <span className="flex items-baseline gap-3">
                <span className={cn("font-serif text-2xl font-light leading-none", isActive ? "text-white" : "text-muted")}>0{i + 1}</span>
                <span className={cn("text-[15px] tracking-nav", isActive ? "text-white" : "text-muted group-hover:text-white")}>{s.label}</span>
                {done[s.to] && <Check className={cn("h-3.5 w-3.5 self-center", isActive ? "text-white" : "text-muted")} />}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <Outlet context={{ detail: data, brandId: Number(brandId), base } satisfies CampaignCtx} />
    </div>
  );
}
