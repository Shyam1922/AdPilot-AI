import { useNavigate } from "react-router-dom";
import { ArrowRight, X } from "lucide-react";
import { Card, Chip, ModeBadge } from "@/components/ui";
import { cn } from "@/lib/format";
import GenerateConcepts from "@/components/GenerateConcepts";
import { useCampaign } from "../Campaign";
import { channelLabel } from "../Campaigns";

export default function Strategy() {
  const { detail, base } = useCampaign();
  const s = detail.campaign.strategy;

  if (!s?.positioning_statement) {
    return <p className="text-sm text-muted">No strategy has been generated for this campaign.</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-line bg-surface p-6 sm:p-10">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-muted">Positioning</span>
          <ModeBadge mode={detail.campaign.generation_mode} />
        </div>
        <p className="display text-[24px] leading-[1.3] sm:text-[32px] sm:leading-[1.25]">{s.positioning_statement}</p>
        <p className="mt-6 text-sm text-muted">
          Primary KPI <span className="ml-2 text-white">{s.primary_kpi}</span>
        </p>
      </section>

      <div className={cn("grid gap-6", s.segments.length >= 2 && "md:grid-cols-2", s.segments.length >= 3 && "lg:grid-cols-3")}>
        {s.segments.map((seg) => (
          <Card key={seg.name} title={seg.name}>
            <ul className="space-y-1.5 text-sm text-ink/80">
              {seg.pain_points.map((p) => (
                <li key={p}>· {p}</li>
              ))}
            </ul>
            <p className="mt-4 border-l-2 border-white pl-3 text-sm text-ink">{seg.message}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Creative direction">
          <ChipGroup label="Themes" items={s.campaign_themes} />
          <ChipGroup label="Angles" items={s.creative_angles} />
          <ChipGroup label="Calls to action" items={s.ctas} />
        </Card>
        <Card title="Channel plan">
          <div className="divide-y divide-line">
            {s.channel_plan.map((c) => (
              <div key={c.channel} className="py-3 first:pt-0 last:pb-0">
                <div className="flex items-baseline justify-between gap-3">
                  <p className="font-medium text-ink">{channelLabel(c.channel)}</p>
                  <p className="text-xs text-muted">{c.formats.join(" · ")}</p>
                </div>
                <p className="mt-0.5 text-sm text-muted">{c.role}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {s.content_calendar.length > 0 && (
        <Card title="First 7 days">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {s.content_calendar.map((d) => (
              <div key={`${d.day}-${d.channel}`} className="rounded-xl bg-surface-2 p-3">
                <p className="text-xs font-medium text-white">Day {d.day}</p>
                <p className="mt-1 text-xs text-muted">{channelLabel(d.channel)}</p>
                <p className="mt-2 text-sm leading-snug text-ink/90">{d.content}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Assumptions">
          <ul className="space-y-2 text-sm text-ink/80">
            {s.assumptions.map((a) => (
              <li key={a}>· {a}</li>
            ))}
          </ul>
        </Card>
        <Card title="Not claimed">
          <ul className="space-y-2 text-sm text-ink/80">
            {s.not_claimed.map((a) => (
              <li key={a} className="flex items-start gap-2">
                <X className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" /> {a}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <NextStep hasConcepts={detail.concepts.length > 0} campaignId={detail.campaign.id} base={base} />
    </div>
  );
}

function ChipGroup({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mb-4 last:mb-0">
      <p className="mb-2 text-xs text-muted">{label}</p>
      <div className="flex flex-wrap gap-2">
        {items.map((t) => (
          <Chip key={t}>{t}</Chip>
        ))}
      </div>
    </div>
  );
}

function NextStep({ hasConcepts, campaignId, base }: { hasConcepts: boolean; campaignId: number; base: string }) {
  const navigate = useNavigate();
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-line bg-surface px-6 py-5">
      <div>
        <p className="font-medium text-ink">{hasConcepts ? "Creatives are ready" : "Next: creatives"}</p>
        <p className="text-sm text-muted">
          {hasConcepts ? "Edit, render videos and approve them." : "Five concepts, one per angle, each with platform copy and a video script."}
        </p>
      </div>
      {hasConcepts ? (
        <button className="btn-primary" onClick={() => navigate(`${base}/creatives`)}>
          Open creatives <ArrowRight className="h-4 w-4" />
        </button>
      ) : (
        <GenerateConcepts campaignId={campaignId} onDone={() => navigate(`${base}/creatives`)} />
      )}
    </div>
  );
}
