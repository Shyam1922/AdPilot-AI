import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ExternalLink, ImagePlus, Pencil, Plus, Trash2, X } from "lucide-react";
import { api, errorMessage, fileUrl } from "@/lib/api";
import { useSupports, useTitle } from "@/lib/hooks";
import { useToast } from "@/components/toast";
import {
  Card,
  Chip,
  ConfirmDialog,
  EditableTitle,
  EmptyState,
  ErrorState,
  Field,
  ModeBadge,
  PageHeader,
  Skeleton,
  SourceBadge,
  Spinner,
} from "@/components/ui";
import { cn } from "@/lib/format";
import type { Brand, BrandProfile, ProductInfo } from "@/lib/types";

export default function BrandMemory() {
  const { brandId } = useParams();
  const id = Number(brandId);
  const { data: brand, isLoading, error, refetch } = useQuery({ queryKey: ["brand", id], queryFn: () => api.getBrand(id) });
  useTitle(brand?.name);

  if (isLoading) return <BrandSkeleton />;
  if (error || !brand) return <ErrorState error={error} onRetry={() => refetch()} />;

  const p = brand.profile;

  return (
    <div className="space-y-6">
      <Header brand={brand} />

      {brand.warnings.length > 0 && (
        <div className="space-y-2 rounded-2xl border border-amber-400/20 bg-amber-400/5 px-5 py-4">
          {brand.warnings.map((w, i) => (
            <p key={i} className="flex items-start gap-2.5 text-sm text-amber-100/90">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" /> {w}
            </p>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <About brand={brand} className="lg:col-span-2" />
        <ListCard brand={brand} field="value_propositions" title="Value propositions" />
      </div>

      <Products brand={brand} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Audience hypotheses" className="lg:col-span-2">
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
                        "shrink-0 text-xs capitalize",
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
        <ListCard brand={brand} field="differentiators" title="Differentiators" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ApprovedClaims brand={brand} />
        <Unknowns brand={brand} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Guardrails brand={brand} />
        <Learnings brand={brand} />
      </div>

      <DeleteBrand brand={brand} />
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
  // The name lives on the brand and in the profile (videos and copy read the profile), so keep both in step.
  const rename = useMutation({
    mutationFn: (name: string) => api.updateBrand(brand.id, { name, profile: { ...brand.profile, brand_name: name } }),
    onSuccess: (b) => {
      qc.setQueryData(["brand", brand.id], b);
      qc.invalidateQueries({ queryKey: ["brands"] });
      toast.success("Brand renamed");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const vi = brand.profile.visual_identity;
  const swatches = [vi.primary, vi.secondary, vi.accent].filter(Boolean) as string[];

  return (
    <PageHeader
      title={
        <span className="flex min-w-0 items-center gap-4">
          {brand.logo_url ? (
            <img src={fileUrl(brand.logo_url)} alt="" className="h-12 w-12 shrink-0 rounded-xl bg-white object-contain p-1.5" />
          ) : (
            <button
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
              title="Upload logo"
              aria-label="Upload logo"
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-dashed border-line text-muted transition hover:border-white/40 hover:text-white"
            >
              {upload.isPending ? <Spinner /> : <ImagePlus className="h-5 w-5" />}
            </button>
          )}
          <EditableTitle
            value={rename.isPending && rename.variables ? rename.variables : brand.name}
            label="Rename brand"
            saving={rename.isPending}
            onSave={(v) => rename.mutate(v)}
          />
        </span>
      }
      subtitle={
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
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

/* --------------------------- editing Brand Memory --------------------------- */

/** PATCH a modified copy of the profile; the backend validates and stores it whole. */
function useProfileSave(brand: Brand, done: string, onDone: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (edit: (p: BrandProfile) => void) => {
      const profile = structuredClone(brand.profile);
      edit(profile);
      return api.updateBrand(brand.id, { profile });
    },
    onSuccess: (b) => {
      qc.setQueryData(["brand", brand.id], b);
      qc.invalidateQueries({ queryKey: ["brands"] });
      toast.success(done);
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function EditActions({ editing, saving, canSave = true, onEdit, onCancel, onSave }: {
  editing: boolean;
  saving: boolean;
  canSave?: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  if (!editing)
    return (
      <button onClick={onEdit} className="inline-flex items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs text-muted transition hover:text-white">
        <Pencil className="h-3.5 w-3.5" /> Edit
      </button>
    );
  return (
    <span className="flex items-center gap-2">
      <button className="btn-ghost h-7 rounded-lg px-3 text-xs" onClick={onCancel} disabled={saving}>
        Cancel
      </button>
      <button className="btn-primary h-7 rounded-lg px-3 text-xs" onClick={onSave} disabled={saving || !canSave}>
        {saving && <Spinner className="h-3.5 w-3.5" />} Save
      </button>
    </span>
  );
}

function About({ brand, className }: { brand: Brand; className?: string }) {
  const p = brand.profile;
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState(p.description);
  const [tone, setTone] = useState(p.brand_tone);
  const save = useProfileSave(brand, "About saved", () => setEditing(false));
  const start = () => {
    setDescription(p.description);
    setTone(p.brand_tone);
    setEditing(true);
  };

  return (
    <Card
      title="About"
      className={className}
      action={
        <EditActions
          editing={editing}
          saving={save.isPending}
          onEdit={start}
          onCancel={() => setEditing(false)}
          onSave={() =>
            save.mutate((x) => {
              x.description = description.trim();
              x.brand_tone = tone;
            })
          }
        />
      }
    >
      {editing ? (
        <div className="space-y-5">
          <Field label="Description">
            <textarea className="input min-h-[96px] resize-y" value={description} onChange={(e) => setDescription(e.target.value)} autoFocus />
          </Field>
          <TagEditor label="Tone" items={tone} onChange={setTone} />
        </div>
      ) : (
        <>
          <p className="leading-relaxed text-ink/90">{p.description || "No description extracted."}</p>
          {p.brand_tone.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              {p.brand_tone.map((t) => (
                <Chip key={t}>{t}</Chip>
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function ListCard({ brand, field, title }: { brand: Brand; field: "value_propositions" | "differentiators"; title: string }) {
  const items = brand.profile[field];
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const save = useProfileSave(brand, `${title} saved`, () => setEditing(false));

  return (
    <Card
      title={title}
      action={
        <EditActions
          editing={editing}
          saving={save.isPending}
          onEdit={() => {
            setText(items.join("\n"));
            setEditing(true);
          }}
          onCancel={() => setEditing(false)}
          onSave={() =>
            save.mutate((x) => {
              x[field] = lines(text);
            })
          }
        />
      }
    >
      {editing ? (
        <Field label="One per line">
          <textarea className="input min-h-[160px] resize-y" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
        </Field>
      ) : (
        <List items={items} empty="None extracted." />
      )}
    </Card>
  );
}

type ProductDraft = Omit<ProductInfo, "features" | "price"> & { price: string; features: string; added?: boolean };

const toDraft = (p: ProductInfo): ProductDraft => ({ ...p, price: p.price ?? "", features: p.features.join("\n") });

function Products({ brand }: { brand: Brand }) {
  const products = brand.profile.products;
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<ProductDraft[]>([]);
  const save = useProfileSave(brand, "Products saved", () => setEditing(false));

  // Downloaded images (product_N) and videos are matched to products by position, so existing
  // products keep their order and can't be removed here; only trailing products without an image can.
  const lastWithImage = drafts.reduce((last, d, i) => (d.image_url ? i : last), -1);
  const removable = (i: number) => i > lastWithImage && !drafts[i].image_url;
  const set = (i: number, patch: Partial<ProductDraft>) => setDrafts((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const valid = drafts.every((d) => d.name.trim());

  return (
    <Card
      title={`Products · ${products.length}`}
      action={
        <EditActions
          editing={editing}
          saving={save.isPending}
          canSave={valid}
          onEdit={() => {
            setDrafts(products.map(toDraft));
            setEditing(true);
          }}
          onCancel={() => setEditing(false)}
          onSave={() =>
            save.mutate((x) => {
              x.products = drafts.map(({ added: _added, ...d }) => ({
                ...d,
                name: d.name.trim(),
                description: d.description.trim(),
                price: d.price.trim() || null,
                features: lines(d.features),
              }));
            })
          }
        />
      }
    >
      {editing ? (
        <div className="space-y-4">
          {drafts.map((d, i) => (
            <div key={i} className="grid gap-4 rounded-xl bg-surface-2 p-4 sm:grid-cols-2">
              <Field label="Name">
                <input className="input" value={d.name} onChange={(e) => set(i, { name: e.target.value })} autoFocus={d.added} />
              </Field>
              <Field label="Price" hint="Leave empty if the site doesn't state one.">
                <input className="input" value={d.price} onChange={(e) => set(i, { price: e.target.value })} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Description">
                  <textarea className="input min-h-[64px] resize-y" value={d.description} onChange={(e) => set(i, { description: e.target.value })} />
                </Field>
              </div>
              <div className="sm:col-span-2">
                <Field label="Features" hint="One per line">
                  <textarea className="input min-h-[80px] resize-y" value={d.features} onChange={(e) => set(i, { features: e.target.value })} />
                </Field>
              </div>
              {removable(i) && (
                <button
                  className="inline-flex items-center gap-1.5 justify-self-start text-xs text-muted transition hover:text-danger"
                  onClick={() => setDrafts((ds) => ds.filter((_, j) => j !== i))}
                >
                  <Trash2 className="h-3.5 w-3.5" /> Remove product
                </button>
              )}
            </div>
          ))}
          <button
            className="btn-ghost"
            onClick={() => setDrafts((ds) => [...ds, { name: "", description: "", price: "", image_url: null, features: "", added: true }])}
          >
            <Plus className="h-4 w-4" /> Add product
          </button>
          {!valid && <p className="text-xs text-warn">Every product needs a name.</p>}
        </div>
      ) : products.length === 0 ? (
        <p className="text-sm text-muted">No products yet. Add them so strategies and creatives can name them.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((prod, i) => (
            <div key={`${i}-${prod.name}`} className="rounded-xl bg-surface-2 p-4">
              <div className="flex items-center gap-3">
                <ProductImage brand={brand} index={i} />
                <div className="min-w-0">
                  <p className="font-medium text-ink">{prod.name}</p>
                  {prod.price && <p className="text-sm text-white">{prod.price}</p>}
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
      )}

      <Photos brand={brand} />
    </Card>
  );
}

/** Every stored brand image. Uploads aren't tied to one product: the newest upload is used in all video ads. */
function Photos({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadBrandFile(brand.id, file, "product"),
    onSuccess: (b) => {
      qc.setQueryData(["brand", brand.id], b);
      toast.success("Photo uploaded");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const isUpload = (u: string) => /\/upload_\d+\.\w+$/.test(u);
  const inVideos = brand.product_image_urls.find(isUpload);

  return (
    <div className="mt-6 border-t border-line pt-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm font-medium text-white">Photos</p>
        <p className="text-xs text-muted">
          {inVideos ? "The newest upload is used in every video ad." : "Upload a photo to use it in every video ad."}
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        {brand.product_image_urls.map((u) => (
          <figure key={u} className="relative">
            <img src={fileUrl(u)} alt="" className="h-24 w-24 rounded-xl bg-white object-contain p-1.5" />
            {u === inVideos && (
              <figcaption className="absolute inset-x-1 bottom-1 rounded-md bg-black/75 px-1 py-0.5 text-center text-[10px] text-white">Used in videos</figcaption>
            )}
          </figure>
        ))}
        <button
          onClick={() => input.current?.click()}
          disabled={upload.isPending}
          className="flex h-24 w-24 flex-col items-center justify-center gap-1.5 rounded-xl bg-raised text-xs text-muted transition hover:bg-[#2b2b2b] hover:text-white"
        >
          {upload.isPending ? <Spinner /> : <ImagePlus className="h-5 w-5" />}
          Upload
        </button>
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
      </div>
    </div>
  );
}

/** Only rendered once the backend exposes DELETE /api/brands/{id}. */
function DeleteBrand({ brand }: { brand: Brand }) {
  const supported = useSupports("delete", "/api/brands/{id}");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteBrand(brand.id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["brand", brand.id] });
      qc.invalidateQueries({ queryKey: ["brands"] });
      toast.success(`${brand.name} deleted`);
      navigate("/");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!supported) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
      <div>
        <p className="text-sm font-medium text-white">Delete brand</p>
        <p className="text-sm text-muted">Removes its memory, campaigns, creatives and metrics.</p>
      </div>
      <button className="btn-danger" onClick={() => setOpen(true)}>
        <Trash2 className="h-4 w-4" /> Delete brand
      </button>
      {open && (
        <ConfirmDialog
          title={`Delete ${brand.name}?`}
          body="Its Brand Memory, campaigns, creatives, videos and metrics will be removed. This can't be undone."
          confirmLabel="Delete"
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
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

/** Unknowns are open questions, not facts: answer one with a fact (saved as a user-provided claim) or dismiss it. */
function Unknowns({ brand }: { brand: Brand }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [answering, setAnswering] = useState<string | null>(null);
  const [fact, setFact] = useState("");
  const resolve = useMutation({
    mutationFn: ({ unknown, claim }: { unknown: string; claim?: string }) => {
      const profile = structuredClone(brand.profile);
      if (claim) profile.approved_claims.push({ claim, source: "user-provided" });
      profile.unknowns_to_confirm = profile.unknowns_to_confirm.filter((u) => u !== unknown);
      return api.updateBrand(brand.id, { profile });
    },
    onSuccess: (b, { claim }) => {
      qc.setQueryData(["brand", brand.id], b);
      setAnswering(null);
      setFact("");
      toast.success(claim ? "Added to approved claims" : "Dismissed");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const items = brand.profile.unknowns_to_confirm;

  return (
    <Card title={`To confirm · ${items.length}`}>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing open. Every claim in use has a source.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((u) => (
            <li key={u} className="rounded-lg bg-amber-400/5 px-3 py-2.5 ring-1 ring-amber-400/15">
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm text-amber-100/90">{u}</span>
                {answering !== u && (
                  <span className="flex shrink-0 items-center gap-3 text-xs">
                    <button className="font-medium text-white underline-offset-4 hover:underline" onClick={() => { setAnswering(u); setFact(""); }}>
                      Add fact
                    </button>
                    <button
                      className="text-muted hover:text-ink disabled:opacity-50"
                      disabled={resolve.isPending}
                      onClick={() => resolve.mutate({ unknown: u })}
                    >
                      Dismiss
                    </button>
                  </span>
                )}
              </div>
              {answering === u && (
                <form
                  className="mt-2.5 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (fact.trim()) resolve.mutate({ unknown: u, claim: fact.trim() });
                  }}
                >
                  <input
                    className="input py-1.5"
                    placeholder="State the fact as it may appear in ads"
                    value={fact}
                    onChange={(e) => setFact(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setAnswering(null)}
                    autoFocus
                  />
                  <button type="submit" className="btn-primary h-8 shrink-0 rounded-lg px-3 text-xs" disabled={!fact.trim() || resolve.isPending}>
                    {resolve.isPending ? <Spinner className="h-3.5 w-3.5" /> : "Save"}
                  </button>
                  <button type="button" className="shrink-0 text-xs text-muted hover:text-ink" onClick={() => setAnswering(null)}>
                    Cancel
                  </button>
                </form>
              )}
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
          <button className="btn-primary h-7 rounded-lg px-3 text-xs" onClick={() => save.mutate()} disabled={save.isPending}>
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
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface-2 p-2">
        {items.map((it) => (
          <span key={it} className="inline-flex items-center gap-1 rounded-lg bg-raised px-2 py-1 text-xs text-body">
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

/**
 * The backend downloads product images as storage/brand_{id}/product_{n}.* in the order of
 * products that have an image_url; `image_url` itself stays the original site URL.
 */
function ProductImage({ brand, index }: { brand: Brand; index: number }) {
  const [failed, setFailed] = useState(false);
  const products = brand.profile.products;
  const own = products[index].image_url;
  if (!own || failed) return null;
  const n = products.slice(0, index).filter((p) => p.image_url).length + 1;
  const local = brand.product_image_urls.find((u) => new RegExp(`/product_${n}\\.\\w+$`).test(u));
  return (
    <img
      src={fileUrl(local ?? own)}
      onError={() => setFailed(true)}
      alt=""
      className="h-14 w-14 shrink-0 rounded-lg bg-white object-contain p-1"
    />
  );
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((v) => (
        <li key={v} className="flex items-start gap-2.5 text-sm text-ink/90">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-white/60" />
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
