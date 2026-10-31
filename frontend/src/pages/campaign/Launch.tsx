import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, ExternalLink, Lock } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { Card, EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui";
import type { CampaignStatus, IntegrationStatus } from "@/lib/types";
import { useCampaign } from "../Campaign";

const STEPS: { key: CampaignStatus; label: string }[] = [
  { key: "draft", label: "Draft" },
  { key: "generated", label: "Generated" },
  { key: "approved", label: "Approved" },
  { key: "scheduled", label: "Scheduled" },
  { key: "published", label: "Published" },
];

const INTEGRATION: Record<IntegrationStatus["status"], { label: string; cls: string }> = {
  working: { label: "Working", cls: "text-success" },
  export_only: { label: "Export only", cls: "text-body" },
  simulated: { label: "Simulated", cls: "text-amber-300" },
  not_connected: { label: "Not connected", cls: "text-muted" },
};

export default function Launch() {
  const { detail, base } = useCampaign();
  const qc = useQueryClient();
  const toast = useToast();
  const c = detail.campaign;
  const approved = detail.concepts.filter((x) => x.status === "approved");
  const reached = STEPS.findIndex((s) => s.key === c.status);

  const setStatus = useMutation({
    mutationFn: (status: "approved" | "scheduled") => api.updateCampaign(c.id, { status }),
    onSuccess: (_, status) => {
      qc.invalidateQueries({ queryKey: ["campaign", c.id] });
      qc.invalidateQueries({ queryKey: ["campaigns", c.brand_id] });
      toast.success(status === "approved" ? "Campaign approved" : "Marked as scheduled");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const exportZip = useMutation({
    mutationFn: () => api.exportCampaign(c.id),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${c.name.replace(/[^\w-]+/g, "_") || `campaign_${c.id}`}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center">
          {STEPS.map((s, i) => {
            const done = i <= reached;
            const locked = s.key === "published" && c.status !== "published";
            return (
              <div key={s.key} className="flex flex-1 items-center last:flex-none">
                <div className="flex flex-col items-center gap-2" title={locked ? "Needs a connected ad account" : undefined}>
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold",
                      done ? "bg-white text-black" : "bg-raised text-muted",
                    )}
                  >
                    {locked ? <Lock className="h-3.5 w-3.5" /> : done ? <Check className="h-4 w-4" /> : i + 1}
                  </span>
                  <span className={cn("text-xs", done ? "text-ink" : "text-muted")}>{s.label}</span>
                </div>
                {i < STEPS.length - 1 && <div className={cn("mx-3 mb-6 h-px flex-1", i < reached ? "bg-white" : "bg-line")} />}
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-6">
        <Card title={`Approved creatives · ${approved.length}`}>
          {approved.length === 0 ? (
            <EmptyState
              title="Nothing approved yet"
              hint="Approve at least one concept before approving the campaign or exporting it."
              action={
                <Link to={`${base}/creatives`} className="btn-ghost">
                  Review creatives
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-line">
              {approved.map((x) => (
                <li key={x.id} className="flex items-center justify-between gap-4 py-3 first:pt-0">
                  <Link to={`${base}/creatives?c=${x.id}`} className="group min-w-0">
                    <p className="truncate text-sm text-ink transition group-hover:text-white">{x.headline || x.hook}</p>
                    <p className="text-xs text-muted">
                      <span className="capitalize">{x.concept_type}</span> · {x.target_segment}
                    </p>
                  </Link>
                  <span className={cn("shrink-0 text-xs", x.latest_video?.status === "ready" ? "text-success" : "text-muted")}>
                    {x.latest_video?.status === "ready" ? "Video ready" : "No video"}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-line pt-5">
            {c.status === "generated" && (
              <button className="btn-primary" onClick={() => setStatus.mutate("approved")} disabled={setStatus.isPending || approved.length === 0}>
                {setStatus.isPending ? <Spinner /> : <Check className="h-4 w-4" />} Approve campaign
              </button>
            )}
            {c.status === "approved" && (
              <button className="btn-primary" onClick={() => setStatus.mutate("scheduled")} disabled={setStatus.isPending}>
                {setStatus.isPending && <Spinner />} Mark as scheduled
              </button>
            )}
            <button className="btn-ghost" onClick={() => exportZip.mutate()} disabled={exportZip.isPending || approved.length === 0}>
              {exportZip.isPending ? <Spinner /> : <Download className="h-4 w-4" />} Export ZIP
            </button>
            <span className="text-xs text-muted">Copy CSV, strategy and MP4s for manual upload to any platform.</span>
          </div>
        </Card>

        <Integrations />
      </div>
    </div>
  );
}

function Integrations() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["integrations"], queryFn: api.listIntegrations });
  return (
    <Card title="Channels">
      {isLoading && <Skeleton className="h-40" />}
      {error && <ErrorState error={error} onRetry={() => refetch()} />}
      {data && (
        <ul className="space-y-4">
          {data.map((it) => {
            const s = INTEGRATION[it.status];
            return (
              <li key={it.provider}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-ink">{it.label}</span>
                  <span className={cn("text-xs", s.cls)}>{s.label}</span>
                </div>
                {it.notes && <p className="mt-0.5 text-xs leading-relaxed text-muted">{it.notes}</p>}
                {it.docs_url && (
                  <a href={it.docs_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-muted transition hover:text-white">
                    Docs <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
