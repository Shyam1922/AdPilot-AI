import { Suspense, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Trash2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useSupports, useTitle } from "@/lib/hooks";
import { useToast } from "@/components/toast";
import { ConfirmDialog, EditableTitle, ErrorState, PageFallback, Skeleton, StatusPill } from "@/components/ui";
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
  const { pathname } = useLocation();
  const step = STEPS.find((s) => pathname.endsWith(`/${s.to}`));
  useTitle(step?.label, data?.campaign.name);

  if (isLoading)
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-full max-w-sm" />
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

      <div className="mb-10 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0 flex-[1_1_320px]">
          <h1 className="display flex text-[32px] leading-[1.1] sm:text-[40px]">
            <CampaignName id={c.id} brandId={c.brand_id} name={c.name} />
          </h1>
          <p className="mt-3 text-[15px] text-muted">
            <span className="capitalize">{c.objective}</span> · {c.channels.map(channelLabel).join(", ")}
            {c.product_focus && <> · {c.product_focus}</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={c.status} />
          <DeleteCampaign id={c.id} brandId={c.brand_id} name={c.name} />
        </div>
      </div>

      <nav className="mb-10 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
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

      <Suspense fallback={<PageFallback />}>
        <Outlet context={{ detail: data, brandId: Number(brandId), base } satisfies CampaignCtx} />
      </Suspense>
    </div>
  );
}

function CampaignName({ id, brandId, name }: { id: number; brandId: number; name: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const rename = useMutation({
    mutationFn: (v: string) => api.updateCampaign(id, { name: v }),
    onSuccess: (campaign) => {
      qc.setQueryData<CampaignDetail>(["campaign", id], (d) => (d ? { ...d, campaign } : d));
      qc.invalidateQueries({ queryKey: ["campaigns", brandId] });
      toast.success("Campaign renamed");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return <EditableTitle value={rename.variables && rename.isPending ? rename.variables : name} label="Rename campaign" saving={rename.isPending} onSave={(v) => rename.mutate(v)} />;
}

/** Only rendered once the backend exposes DELETE /api/campaigns/{id}. */
function DeleteCampaign({ id, brandId, name }: { id: number; brandId: number; name: string }) {
  const supported = useSupports("delete", "/api/campaigns/{id}");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteCampaign(id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["campaign", id] });
      qc.invalidateQueries({ queryKey: ["campaigns", brandId] });
      toast.success("Campaign deleted");
      navigate(`/brands/${brandId}/campaigns`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!supported) return null;
  return (
    <>
      <button className="btn-ghost w-9 px-0 text-muted hover:text-danger" onClick={() => setOpen(true)} aria-label="Delete campaign" title="Delete campaign">
        <Trash2 className="h-4 w-4" />
      </button>
      {open && (
        <ConfirmDialog
          title="Delete campaign?"
          body={<>“{name}”, its creatives, videos and metrics will be removed. This can't be undone.</>}
          confirmLabel="Delete"
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
