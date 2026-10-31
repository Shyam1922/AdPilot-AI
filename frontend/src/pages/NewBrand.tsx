import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Plus } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/format";
import { useToast } from "@/components/toast";
import { ErrorState, Field, Spinner } from "@/components/ui";
import TopBar, { HeroGlow } from "@/components/TopBar";
import { useTitle } from "@/lib/hooks";
import type { ManualBrandInput } from "@/lib/types";

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

const STEPS = [
  { title: "Read the brand", body: "Products, claims and tone become Brand Memory. Every claim keeps its source." },
  { title: "Plan and create", body: "A strategy per campaign, then concepts with platform copy, a claim check and a video." },
  { title: "Launch and learn", body: "Export for upload, bring results back, and what worked feeds the next round." },
];

export default function NewBrand() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: brands } = useQuery({ queryKey: ["brands"], queryFn: api.listBrands });
  useTitle("Add brand");
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
    <div className="relative isolate min-h-screen bg-canvas">
      <HeroGlow />
      <TopBar
        right={
          !!brands?.length && (
            <Link to="/" className="btn-ghost">
              Your brands
            </Link>
          )
        }
      />

      <div className="mx-auto max-w-2xl px-4 pb-20 pt-14 sm:px-6 sm:pb-28 sm:pt-24">
        <h1 className="display text-center text-[40px] leading-[1.04] sm:text-[54px]">Turn a website into a campaign</h1>
        <p className="mx-auto mt-5 max-w-lg text-center text-[17px] text-muted">
          AdPilot reads your site, keeps only claims it can source, and lists anything it can't verify for you to confirm.
        </p>

        <form
          className="mt-12"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) analyze.mutate();
          }}
        >
          <div className="rounded-2xl border border-white/[0.08] bg-[#16171a]/95 shadow-panel transition focus-within:border-white/35">
            <input
              className="w-full bg-transparent px-5 pb-8 pt-5 text-base font-medium text-white outline-none placeholder:font-normal placeholder:text-muted"
              placeholder="Paste a website or product page…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={analyze.isPending}
              autoFocus
            />

            {manualOpen && (
              <div className="grid gap-4 border-t border-white/[0.06] px-5 py-5 text-left sm:grid-cols-2">
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

            <div className="flex items-center justify-between gap-3 px-4 pb-4">
              <button
                type="button"
                onClick={() => setManualOpen((o) => !o)}
                className="inline-flex items-center gap-2 text-sm font-medium text-white"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-raised transition hover:bg-[#2b2b2b]">
                  <Plus className={cn("h-4 w-4 transition", manualOpen && "rotate-45")} />
                </span>
                {manualOpen ? "Hide details" : "Add details"}
              </button>
              <div className="flex items-center gap-3">
                {analyze.isPending && (
                  <span className="hidden items-center gap-2 text-[13px] text-muted sm:inline-flex">
                    <Spinner className="h-3.5 w-3.5" /> Reading the brand, 5–25 seconds
                  </span>
                )}
                <button
                  type="submit"
                  disabled={!canSubmit}
                  aria-label="Build Brand Memory"
                  title="Build Brand Memory"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-black transition hover:bg-white/85 disabled:bg-raised disabled:text-muted"
                >
                  {analyze.isPending ? <Spinner className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </div>

          {analyze.isError && (
            <div className="mt-4">
              <ErrorState error={new Error(errorMessage(analyze.error))} />
            </div>
          )}
          <p className="mt-5 text-center text-[13px] text-white/45">Needs a URL or at least a brand name.</p>
        </form>
      </div>

      <section className="mx-auto max-w-6xl px-4 pb-28 sm:px-6">
        <div className="grid gap-10 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={s.title} className="border-t border-line pt-6">
              <p className="display text-[32px] leading-none text-muted">0{i + 1}</p>
              <p className="mt-6 text-xl font-medium text-[#f0f0f0]">{s.title}</p>
              <p className="mt-2 text-base leading-relaxed text-muted">{s.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
