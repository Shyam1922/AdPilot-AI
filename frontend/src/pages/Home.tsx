import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus } from "lucide-react";
import { api, fileUrl } from "@/lib/api";
import { ApiOffline, ErrorState, Skeleton } from "@/components/ui";
import Logo from "@/components/Logo";

export default function Home() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const brands = useQuery({ queryKey: ["brands"], queryFn: api.listBrands, enabled: health.isSuccess });

  if (health.isError) return <ApiOffline onRetry={() => health.refetch()} />;
  if (brands.data && brands.data.length === 0) return <Navigate to="/brands/new" replace />;

  return (
    <div className="min-h-screen bg-canvas">
      <div className="mx-auto max-w-3xl px-6 py-14">
        <div className="mb-14 flex items-center justify-between">
          <Logo />
          <Link to="/brands/new" className="btn-primary">
            <Plus className="h-4 w-4" /> Add brand
          </Link>
        </div>

        <h1 className="font-serif text-3xl font-semibold text-ink">Your brands</h1>
        <p className="mt-2 text-sm text-muted">Each brand keeps its own memory: products, claims, tone and what has worked.</p>

        <div className="mt-8 space-y-3">
          {brands.isError && <ErrorState error={brands.error} onRetry={() => brands.refetch()} />}
          {(health.isLoading || brands.isLoading) && [0, 1].map((i) => <Skeleton key={i} className="h-20" />)}
          {brands.data?.map((b) => (
            <Link
              key={b.id}
              to={`/brands/${b.id}`}
              className="group flex items-center gap-4 rounded-xl border border-line bg-surface px-5 py-4 transition hover:border-brand-500/40 hover:bg-surface-2"
            >
              {b.logo_url ? (
                <img src={fileUrl(b.logo_url)} alt="" className="h-11 w-11 rounded-lg bg-white object-contain p-1" />
              ) : (
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-brand-600 font-semibold text-white">
                  {b.name.slice(0, 1).toUpperCase()}
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">{b.name}</p>
                <p className="truncate text-sm text-muted">{b.website || b.profile.product_category || "Added manually"}</p>
              </div>
              <ArrowRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-brand-400" />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
