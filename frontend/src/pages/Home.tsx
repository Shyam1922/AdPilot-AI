import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, fileUrl } from "@/lib/api";
import { ApiOffline, ErrorState, Skeleton } from "@/components/ui";
import TopBar, { HeroGlow } from "@/components/TopBar";
import { useTitle } from "@/lib/hooks";

export default function Home() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const brands = useQuery({ queryKey: ["brands"], queryFn: api.listBrands, enabled: health.isSuccess });
  useTitle("Brands");

  if (brands.data && brands.data.length === 0) return <Navigate to="/brands/new" replace />;

  return (
    <div className="relative isolate min-h-screen bg-canvas">
      <HeroGlow />
      <TopBar
        right={
          <Link to="/brands/new" className="btn-primary">
            <Plus className="h-4 w-4" /> Add brand
          </Link>
        }
      />

      {health.isError ? (
        <ApiOffline onRetry={() => health.refetch()} />
      ) : (
        <div className="mx-auto max-w-6xl px-4 pb-24 pt-14 sm:px-6 sm:pt-20">
          <div className="mx-auto max-w-2xl text-center">
            <h1 className="display text-[40px] leading-[1.02] sm:text-[54px]">Your brands</h1>
            <p className="mt-4 text-[17px] text-muted">Each brand keeps its own memory: products, claims, tone and what has worked.</p>
          </div>

          <div className="mt-12 grid gap-6 sm:mt-16 sm:grid-cols-2 lg:grid-cols-3">
            {brands.isError && (
              <div className="sm:col-span-2 lg:col-span-3">
                <ErrorState error={brands.error} onRetry={() => brands.refetch()} />
              </div>
            )}
            {(health.isLoading || brands.isLoading) && [0, 1, 2].map((i) => <Skeleton key={i} className="aspect-[4/3]" />)}
            {brands.data?.map((b) => (
              <Link key={b.id} to={`/brands/${b.id}`} className="group">
                <div className="flex aspect-[4/3] items-center justify-center rounded-2xl border border-line bg-surface transition group-hover:border-white/20 group-hover:bg-surface-2">
                  {b.logo_url ? (
                    <img src={fileUrl(b.logo_url)} alt="" className="h-20 w-20 rounded-2xl bg-white object-contain p-2" />
                  ) : (
                    <span className="display text-[64px] leading-none text-white/90">{b.name.slice(0, 1).toUpperCase()}</span>
                  )}
                </div>
                <p className="mt-4 text-[17px] font-medium text-white">{b.name}</p>
                <p className="mt-1 truncate text-[15px] text-muted">{b.website?.replace(/^https?:\/\//, "").replace(/\/$/, "") || b.profile.product_category || "Added manually"}</p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
