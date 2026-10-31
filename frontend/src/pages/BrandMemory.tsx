import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ExternalLink, ImagePlus, Plus, X } from "lucide-react";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Card, Chip, EmptyState, ErrorState, ModeBadge, PageHeader, Skeleton, SourceBadge, Spinner } from "@/components/ui";
import { cn } from "@/lib/format";
import type { Brand } from "@/lib/types";

export default function BrandMemory() {
  const { brandId } = useParams();
  const id = Number(brandId);
  const { data: brand, isLoading, error, refetch } = useQuery({ queryKey: ["brand", id], queryFn: () => api.getBrand(id) });

  if (isLoading) return <BrandSkeleton />;
  if (error || !brand) return <ErrorState error={error} onRetry={() => refetch()} />;

  const p = brand.profile;

  return (
    <div className="space-y-6">
      <Header brand={brand} />

      {brand.warnings.length > 0 && (
        <div className="space-y-2 rounded-xl border border-amber-400/20 bg-amber-400/5 px-5 py-4">
          {brand.warnings.map((w, i) => (
            <p key={i} className="flex items-start gap-2.5 text-sm text-amber-100/90">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" /> {w}
            </p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        <Card title="About" className="col-span-2">
          <p className="leading-relaxed text-ink/90">{p.description || "No description extracted."}</p>
          {p.brand_tone.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              {p.brand_tone.map((t) => (
                <Chip key={t}>{t}</Chip>
              ))}
            </div>
          )}
        </Card>
        <Card title="Value propositions">
          <List items={p.value_propositions} empty="None extracted." />
        </Card>
      </div>

      {p.products.length > 0 && (
        <Card title={`Products · ${p.products.length}`}>
          <div className="grid grid-cols-3 gap-4">
            {p.products.map((prod) => (
              <div key={prod.name} className="rounded-xl bg-white/[0.03] p-4 ring-1 ring-white/5">
                <div className="flex items-center gap-3">
                  {prod.image_url && <img src={fileUrl(prod.image_url)} alt="" className="h-14 w-14 rounded-lg bg-white object-contain p-1" />}
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{prod.name}</p>
                    {prod.price && <p className="text-sm text-brand-300">{prod.price}</p>}
                  </div>
                </div>
                {prod.description && <p className="mt-3 text-sm text-muted">{prod.description}</p>}
                {prod.features.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm text-ink/80">
                    {prod.features.map((f) => (
                      <li key={f}>· {f}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-6">
        <Card title="Audience hypotheses" className="col-span-2">
          {p.audience_hypotheses.length === 0 ? (
            <p className="text-sm text-muted">None yet.</p>
          ) : (
            <div className="divide-y divide-line">
              {p.audience_hypotheses.map((a) => (
                <div key={a.segment} className="py-3 first:pt-0 last:pb-0">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-ink">{a.segment}</p>
                    <span
                      className={cn(
                        "text-xs capitalize",
                        a.confidence === "high" ? "text-success" : a.confidence === "medium" ? "text-warn" : "text-muted",
                      )}
                    >
                      {a.confidence} confidence
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-ink/80">{a.need}</p>
                  <p className="mt-1 text-xs text-muted">Evidence: {a.evidence}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Differentiators">
          <List items={p.differentiators} empty="None extracted." />
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <ApprovedClaims brand={brand} />
        <Unknowns brand={brand} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <Guardrails brand={brand} />
        <Learnings brand={brand} />
      </div>
    </div>
  );
}

function Header({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadBrandFile(brand.id, file, "logo"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["brand", brand.id] });
      qc.invalidateQueries({ queryKey: ["brands"] });
      toast.success("Logo uploaded");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const vi = brand.profile.visual_identity;
  const swatches = [vi.primary, vi.secondary, vi.accent].filter(Boolean) as string[];

  return (
    <PageHeader
      title={
        <span className="flex items-center gap-4">
          {brand.logo_url ? (
            <img src={fileUrl(brand.logo_url)} alt="" className="h-12 w-12 rounded-xl bg-white object-contain p-1.5" />
          ) : (
            <button
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
              title="Upload logo"
              className="flex h-12 w-12 items-center justify-center rounded-xl border border-dashed border-line text-muted transition hover:border-brand-500 hover:text-brand-400"
            >
              {upload.isPending ? <Spinner /> : <ImagePlus className="h-5 w-5" />}
            </button>
          )}
          {brand.name}
        </span>
      }
      subtitle={
        <span className="flex items-center gap-3">
          {brand.website && (
            <a href={brand.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink">
              {brand.website.replace(/^https?:\/\//, "").replace(/\/$/, "")} <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {brand.profile.product_category && <span>{brand.profile.product_category}</span>}
          <ModeBadge mode={brand.generation_mode} />
        </span>
      }
      action={
        <>
          {swatches.map((c) => (
            <span key={c} title={c} className="h-7 w-7 rounded-full ring-2 ring-white/10" style={{ background: c }} />
          ))}
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
              e.target.value = "";
            }}
          />
        </>
      }
    />
  );
}

function ApprovedClaims({ brand }: { brand: Brand }) {
  const claims = brand.profile.approved_claims;
  const sourceLabel = (src: string) => {
    const id = src.replace(/^page:/, "");
    const snippet = brand.sources.find((s) => s.id === id);
    if (snippet) return { label: id, title: snippet.text };
    if (src === "user-provided") return { label: "you", title: "Provided or confirmed by you" };
    if (/^https?:\/\//.test(src)) return { label: new URL(src).hostname, title: src };
    return { label: src, title: src };
  };
  return (
    <Card title={`Approved claims · ${claims.length}`}>
      {claims.length === 0 ? (
        <p className="text-sm text-muted">No sourced claims yet. Confirm unknowns to add them.</p>
      ) : (
        <ul className="divide-y divide-line">
          {claims.map((c) => {
            const s = sourceLabel(c.source);
            return (
              <li key={c.claim} className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
                <span className="flex items-start gap-2 text-sm text-ink/90">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" /> {c.claim}
                </span>
                <span title={s.title} className="shrink-0 cursor-help font-mono text-[11px] text-muted">
                  {s.label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function Unknowns({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useMutation({
    mutationFn: (text: string) => {
      const profile = structuredClone(brand.profile);
      profile.approved_claims.push({ claim: text, source: "user-provided" });
      profile.unknowns_to_confirm = profile.unknowns_to_confirm.filter((u) => u !== text);
      return api.updateBrand(brand.id, { profile });
    },
    onSuccess: (b) => {
      qc.setQueryData(["brand", brand.id], b);
      toast.success("Added to approved claims");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const items = brand.profile.unknowns_to_confirm;

  return (
    <Card title={`To confirm · ${items.length}`}>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing to confirm. Every claim in use has a source.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((u) => (
            <li key={u} className="flex items-center justify-between gap-3 rounded-lg bg-amber-400/5 px-3 py-2.5 ring-1 ring-amber-400/15">
              <span className="text-sm text-amber-100/90">{u}</span>
              <button
                className="shrink-0 text-xs font-medium text-brand-300 hover:text-white disabled:opacity-50"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate(u)}
              >
                {confirm.isPending && confirm.variables === u ? "Saving…" : "Confirm as true"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Guardrails({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const g = brand.guardrails;
  const [claims, setClaims] = useState<string[]>(g.claims_to_avoid ?? []);
  const [words, setWords] = useState<string[]>(g.words_to_avoid ?? []);
  const [notes, setNotes] = useState(g.notes ?? "");
  useEffect(() => {
    setClaims(g.claims_to_avoid ?? []);
    setWords(g.words_to_avoid ?? []);
    setNotes(g.notes ?? "");
  }, [g.claims_to_avoid, g.words_to_avoid, g.notes]);

  const dirty =
    JSON.stringify(claims) !== JSON.stringify(g.claims_to_avoid ?? []) ||
    JSON.stringify(words) !== JSON.stringify(g.words_to_avoid ?? []) ||
    notes !== (g.notes ?? "");

  const save = useMutation({
    mutationFn: () => api.updateBrand(brand.id, { guardrails: { claims_to_avoid: claims, words_to_avoid: words, notes } }),
    onSuccess: (b) => {
      qc.setQueryData(["brand", brand.id], b);
      toast.success("Guardrails saved");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Card
      title="Guardrails"
      action={
        dirty && (
          <button className="btn-primary px-3 py-1.5 text-xs" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending && <Spinner className="h-3.5 w-3.5" />} Save
          </button>
        )
      }
    >
      <div className="space-y-5">
        <TagEditor label="Claims to avoid" items={claims} onChange={setClaims} />
        <TagEditor label="Words to avoid" items={words} onChange={setWords} />
        <label className="block">
          <span className="label">Notes</span>
          <textarea className="input min-h-[64px] resize-y" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </div>
    </Card>
  );
}

function TagEditor({ label, items, onChange }: { label: string; items: string[]; onChange: (x: string[]) => void }) {
  const [value, setValue] = useState("");
  const add = () => {
    const v = value.trim();
    if (v && !items.includes(v)) onChange([...items, v]);
    setValue("");
  };
  return (
    <div>
      <span className="label">{label}</span>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface-2 p-2">
        {items.map((it) => (
          <span key={it} className="inline-flex items-center gap-1 rounded-md bg-white/5 px-2 py-1 text-xs text-ink/90 ring-1 ring-white/10">
            {it}
            <button onClick={() => onChange(items.filter((x) => x !== it))} className="text-muted hover:text-danger">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          className="min-w-[120px] flex-1 bg-transparent px-1 py-1 text-sm text-ink outline-none placeholder:text-muted/60"
          placeholder="Add and press Enter"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        {value && (
          <button onClick={add} className="text-muted hover:text-ink">
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}

function Learnings({ brand }: { brand: Brand }) {
  return (
    <Card title="Learnings">
      {brand.learnings.length === 0 ? (
        <EmptyState title="No learnings yet" hint="They're written here after a campaign's first optimization round." />
      ) : (
        <ul className="space-y-4">
          {brand.learnings.map((l, i) => (
            <li key={i}>
              <p className="text-sm leading-relaxed text-ink/90">{l.text}</p>
              <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
                <SourceBadge source={l.data_source} />
                <span>Iteration #{l.iteration_id}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((v) => (
        <li key={v} className="flex items-start gap-2.5 text-sm text-ink/90">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
          {v}
        </li>
      ))}
    </ul>
  );
}

function BrandSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-14 w-72" />
      <div className="grid grid-cols-3 gap-6">
        <Skeleton className="col-span-2 h-40" />
        <Skeleton className="h-40" />
      </div>
      <Skeleton className="h-48" />
    </div>
  );
}
