import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, Link2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { ErrorState, Field, Spinner } from "@/components/ui";
import Logo from "@/components/Logo";
import type { ManualBrandInput } from "@/lib/types";

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function NewBrand() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [m, setM] = useState({
    brand_name: "",
    product_name: "",
    product_description: "",
    target_audience: "",
    price_range: "",
    tone: "",
    key_features: "",
    claims_to_avoid: "",
  });
  const set = (k: keyof typeof m) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setM({ ...m, [k]: e.target.value });

  const analyze = useMutation({
    mutationFn: () => {
      const manual: ManualBrandInput = {};
      for (const k of ["brand_name", "product_name", "product_description", "target_audience", "price_range", "tone"] as const) {
        if (m[k].trim()) manual[k] = m[k].trim();
      }
      if (m.key_features.trim()) manual.key_features = list(m.key_features);
      if (m.claims_to_avoid.trim()) manual.claims_to_avoid = list(m.claims_to_avoid);
      return api.analyzeBrand({ url: url.trim() || undefined, manual });
    },
    onSuccess: (brand) => {
      qc.invalidateQueries({ queryKey: ["brands"] });
      toast.success(`Brand Memory created for ${brand.name}`);
      navigate(`/brands/${brand.id}`);
    },
    onError: () => setManualOpen(true),
  });

  const canSubmit = (url.trim() || m.brand_name.trim()) && !analyze.isPending;

  return (
    <div className="min-h-screen bg-canvas">
      <div className="mx-auto max-w-xl px-6 py-14">
        <div className="mb-14 flex items-center justify-between">
          <Logo />
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
            <ArrowLeft className="h-4 w-4" /> Brands
          </Link>
        </div>

        <h1 className="font-serif text-3xl font-semibold leading-tight text-ink">Add a brand</h1>
        <p className="mt-3 text-muted">
          Paste a website or product page. AdPilot reads it, keeps only claims it can source, and lists anything it can't verify for you to confirm.
        </p>

        <form
          className="mt-10 space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) analyze.mutate();
          }}
        >
          <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 transition focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/25">
            <Link2 className="h-4 w-4 shrink-0 text-muted" />
            <input
              className="w-full bg-transparent py-3.5 text-[15px] text-ink outline-none placeholder:text-muted/60"
              placeholder="https://yourbrand.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={analyze.isPending}
              autoFocus
            />
          </div>

          <button
            type="button"
            onClick={() => setManualOpen((o) => !o)}
            className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink"
          >
            <ChevronDown className={cn("h-4 w-4 transition", manualOpen && "rotate-180")} />
            Add details manually
          </button>

          {manualOpen && (
            <div className="grid grid-cols-2 gap-4 rounded-xl border border-line bg-surface p-5">
              <Field label="Brand name">
                <input className="input" value={m.brand_name} onChange={set("brand_name")} />
              </Field>
              <Field label="Product name">
                <input className="input" value={m.product_name} onChange={set("product_name")} />
              </Field>
              <div className="col-span-2">
                <Field label="Product description">
                  <textarea className="input min-h-[80px] resize-y" value={m.product_description} onChange={set("product_description")} />
                </Field>
              </div>
              <Field label="Target audience">
                <input className="input" value={m.target_audience} onChange={set("target_audience")} />
              </Field>
              <Field label="Price range">
                <input className="input" value={m.price_range} onChange={set("price_range")} />
              </Field>
              <Field label="Tone">
                <input className="input" value={m.tone} onChange={set("tone")} />
              </Field>
              <Field label="Key features" hint="Comma separated">
                <input className="input" value={m.key_features} onChange={set("key_features")} />
              </Field>
              <div className="col-span-2">
                <Field label="Claims to avoid" hint="Comma separated. The claim guard flags these in every creative.">
                  <input className="input" value={m.claims_to_avoid} onChange={set("claims_to_avoid")} />
                </Field>
              </div>
            </div>
          )}

          {analyze.isError && <ErrorState error={new Error(errorMessage(analyze.error))} />}

          <button type="submit" className="btn-primary w-full py-3" disabled={!canSubmit}>
            {analyze.isPending ? (
              <>
                <Spinner /> Reading the brand — this takes 5–25 seconds
              </>
            ) : (
              "Build Brand Memory"
            )}
          </button>
          <p className="text-center text-xs text-muted">Needs a URL or at least a brand name.</p>
        </form>
      </div>
    </div>
  );
}
