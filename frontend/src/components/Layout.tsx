import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { ApiOffline, PageFallback } from "./ui";
import TopBar from "./TopBar";

export default function Layout() {
  const { brandId } = useParams();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });

  if (health.isError) {
    return (
      <div className="min-h-screen bg-canvas">
        <TopBar />
        <ApiOffline onRetry={() => health.refetch()} />
      </div>
    );
  }

  const nav = [
    { to: `/brands/${brandId}`, label: "Brand Memory", end: true },
    { to: `/brands/${brandId}/campaigns`, label: "Campaigns", end: false },
  ];

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <TopBar
        nav={nav.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => cn("text-[15px] tracking-nav transition", isActive ? "text-white" : "text-muted hover:text-white")}
          >
            {label}
          </NavLink>
        ))}
        right={<BrandSwitcher currentId={Number(brandId)} />}
      />

      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
          <Suspense fallback={<PageFallback />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      <footer className="border-t border-white/[0.08]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-5 text-xs text-muted sm:px-6">
          <StatusRow ok={!!health.data && health.data.llm_provider !== "offline"} label={health.data ? (health.data.llm_provider === "offline" ? "Offline generator" : health.data.llm_provider.replace(/^\w/, (c) => c.toUpperCase())) : "…"} prefix="LLM" />
          <StatusRow ok={!!health.data?.ffmpeg} label={health.data ? (health.data.ffmpeg ? "FFmpeg ready" : "FFmpeg missing") : "…"} prefix="Video" />
          <span className="w-full sm:ml-auto sm:w-auto">Nothing is published and no money is spent without your approval.</span>
        </div>
      </footer>
    </div>
  );
}

function StatusRow({ ok, label, prefix }: { ok: boolean; label: string; prefix: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-success" : "bg-warn")} />
      {prefix}
      <span className="text-body">{label}</span>
    </span>
  );
}

function BrandSwitcher({ currentId }: { currentId: number }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: brands } = useQuery({ queryKey: ["brands"], queryFn: api.listBrands });
  const current = brands?.find((b) => b.id === currentId);

  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} className="btn-ghost max-w-[220px] pl-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white text-[11px] font-semibold text-black">
          {(current?.name ?? "?").slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 truncate">{current?.name ?? "Loading…"}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted transition", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-60 overflow-hidden rounded-2xl border border-line bg-[#16171a]/95 p-1.5 shadow-panel backdrop-blur-xl">
          {brands?.map((b) => (
            <button
              key={b.id}
              onClick={() => {
                setOpen(false);
                navigate(`/brands/${b.id}`);
              }}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-body hover:bg-white/5 hover:text-white"
            >
              <span className="flex-1 truncate">{b.name}</span>
              {b.id === currentId && <Check className="h-4 w-4 text-white" />}
            </button>
          ))}
          <div className="my-1.5 border-t border-line" />
          <button
            onClick={() => {
              setOpen(false);
              navigate("/brands/new");
            }}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-muted hover:bg-white/5 hover:text-white"
          >
            <Plus className="h-4 w-4" /> Add brand
          </button>
        </div>
      )}
    </div>
  );
}
