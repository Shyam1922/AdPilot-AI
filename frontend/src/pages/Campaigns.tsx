import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Plus, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { EmptyState, ErrorState, Field, PageHeader, Skeleton, Spinner, StatusPill } from "@/components/ui";
import type { Objective } from "@/lib/types";

export const OBJECTIVES: { key: Objective; label: string; hint: string }[] = [
  { key: "awareness", label: "Awareness", hint: "Reach new people" },
  { key: "traffic", label: "Traffic", hint: "Drive site visits" },
  { key: "leads", label: "Leads", hint: "Collect sign-ups" },
  { key: "sales", label: "Sales", hint: "Drive purchases" },
  { key: "engagement", label: "Engagement", hint: "Grow the audience" },
  { key: "launch", label: "Launch", hint: "Introduce a product" },
];

export const CHANNELS: { key: string; label: string }[] = [
  { key: "instagram", label: "Instagram" },
  { key: "meta_ads", label: "Meta Ads" },
  { key: "google_ads", label: "Google Ads" },
];

/** The backend uses channel keys (instagram, meta_ads, …); show readable names. */
export const channelLabel = (c: string) =>
  CHANNELS.find((x) => x.key === c.toLowerCase())?.label ?? c.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

export default function Campaigns() {
  const { brandId } = useParams();
  const id = Number(brandId);
  const [open, setOpen] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["campaigns", id], queryFn: () => api.listCampaigns(id) });

  return (
    <div>
      <PageHeader
        title="Campaigns"
        subtitle="Each campaign runs the loop: strategy, creatives, launch, then learn from performance."
        action={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New campaign
          </button>
        }
      />

      {error && <ErrorState error={error} onRetry={() => refetch()} />}
      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      )}
      {data?.length === 0 && (
        <EmptyState
          title="No campaigns yet"
          hint="Pick an objective and channels. AdPilot writes a strategy grounded in this brand's memory."
          action={
            <button className="btn-primary" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> New campaign
            </button>
          }
        />
      )}

      {!!data?.length && (
        <div className="overflow-hidden rounded-2xl border border-line">
          {[...data].reverse().map((c) => (
            <Link
              key={c.id}
              to={`/brands/${id}/campaigns/${c.id}`}
              className="group flex items-center gap-6 border-b border-line bg-surface px-6 py-5 transition last:border-0 hover:bg-surface-2"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-base font-medium text-white">{c.name}</p>
                <p className="mt-1 text-sm text-muted">
                  <span className="capitalize">{c.objective}</span> · {c.channels.map(channelLabel).join(", ")}
                </p>
              </div>
              <div className="text-right text-sm text-muted">
                <p>
                  {c.counts.concepts} concepts · {c.counts.approved} approved
                </p>
                <p className="text-xs">{c.counts.videos_ready} videos ready</p>
              </div>
              <StatusPill status={c.status} />
              <ArrowRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-white" />
            </Link>
          ))}
        </div>
      )}

      {open && <NewCampaignDialog brandId={id} onClose={() => setOpen(false)} />}
    </div>
  );
}

function NewCampaignDialog({ brandId, onClose }: { brandId: number; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: brand } = useQuery({ queryKey: ["brand", brandId], queryFn: () => api.getBrand(brandId) });
  const products = brand?.profile.products.map((p) => p.name) ?? [];

  const [name, setName] = useState("");
  const [objective, setObjective] = useState<Objective>("sales");
  const [channels, setChannels] = useState<string[]>(CHANNELS.map((c) => c.key));
  const [productFocus, setProductFocus] = useState("");
  const [audience, setAudience] = useState("");
  const [budget, setBudget] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.createCampaign({
        brand_id: brandId,
        name: name.trim() || undefined,
        objective,
        channels,
        product_focus: productFocus || undefined,
        audience_note: audience.trim() || undefined,
        budget_note: budget.trim() || undefined,
      }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["campaigns", brandId] });
      navigate(`/brands/${brandId}/campaigns/${c.id}/strategy`);
    },
  });

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !create.isPending && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, create.isPending]);

  const toggle = (c: string) => setChannels((xs) => (xs.includes(c) ? xs.filter((x) => x !== c) : [...xs, c]));

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={() => !create.isPending && onClose()}>
      <form
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-white/[0.08] bg-[#16171a] shadow-panel"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          if (channels.length) create.mutate();
        }}
      >
        <header className="flex items-center justify-between px-6 pb-2 pt-6">
          <h2 className="display text-[28px] leading-tight">New campaign</h2>
          <button type="button" onClick={onClose} className="text-muted transition hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="space-y-6 px-6 py-4">
          <Field label="Name" hint="Optional">
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </Field>

          <div>
            <span className="label">Objective</span>
            <div className="grid grid-cols-3 gap-2">
              {OBJECTIVES.map((o) => (
                <button
                  type="button"
                  key={o.key}
                  onClick={() => setObjective(o.key)}
                  className={cn(
                    "rounded-xl px-3 py-2.5 text-left transition",
                    objective === o.key ? "bg-white text-black" : "bg-raised hover:bg-[#2b2b2b]",
                  )}
                >
                  <p className={cn("text-sm font-medium", objective === o.key ? "text-black" : "text-white")}>{o.label}</p>
                  <p className={cn("text-xs", objective === o.key ? "text-black/60" : "text-muted")}>{o.hint}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="label">Channels</span>
            <div className="flex flex-wrap gap-2">
              {CHANNELS.map((c) => (
                <button
                  type="button"
                  key={c.key}
                  onClick={() => toggle(c.key)}
                  className={cn(
                    "rounded-xl px-3.5 py-2 text-sm transition",
                    channels.includes(c.key) ? "bg-white text-black" : "bg-raised text-muted hover:text-white",
                  )}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {products.length > 0 && (
            <Field label="Product focus">
              <select className="input" value={productFocus} onChange={(e) => setProductFocus(e.target.value)}>
                <option value="">Whole range</option>
                {products.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </Field>
          )}

          <div className="grid grid-cols-2 gap-4">
            <Field label="Audience note" hint="Optional">
              <input className="input" value={audience} onChange={(e) => setAudience(e.target.value)} />
            </Field>
            <Field label="Budget note" hint="Optional">
              <input className="input" value={budget} onChange={(e) => setBudget(e.target.value)} />
            </Field>
          </div>

          {create.isError && <ErrorState error={new Error(errorMessage(create.error))} />}
        </div>

        <footer className="flex items-center justify-end gap-2 px-6 pb-6 pt-2">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={create.isPending}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={create.isPending || channels.length === 0}>
            {create.isPending ? (
              <>
                <Spinner /> Writing strategy…
              </>
            ) : (
              "Create campaign"
            )}
          </button>
        </footer>
      </form>
    </div>
  );
}
