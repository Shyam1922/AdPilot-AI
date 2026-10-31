import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Brain, Check, ChevronsUpDown, Megaphone, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { ApiOffline } from "./ui";
import Logo from "./Logo";

export default function Layout() {
  const { brandId } = useParams();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });

  if (health.isError) {
    return (
      <div className="min-h-screen bg-canvas">
        <ApiOffline onRetry={() => health.refetch()} />
      </div>
    );
  }

  const nav = [
    { to: `/brands/${brandId}`, label: "Brand Memory", icon: Brain, end: true },
    { to: `/brands/${brandId}/campaigns`, label: "Campaigns", icon: Megaphone, end: false },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-sidebar">
        <Link to="/" className="px-5 pb-6 pt-6">
          <Logo />
        </Link>

        <div className="px-3">
          <BrandSwitcher currentId={Number(brandId)} />
        </div>

        <nav className="mt-6 flex-1 space-y-1 px-3">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                  isActive ? "bg-brand-500/15 text-ink" : "text-muted hover:bg-white/5 hover:text-ink",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn("h-4 w-4", isActive && "text-brand-400")} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-1.5 border-t border-line px-5 py-4 text-xs text-muted">
          <StatusRow ok={health.data?.llm_provider === "gemini"} label={health.data ? (health.data.llm_provider === "gemini" ? "Gemini" : "Offline generator") : "…"} prefix="LLM" />
          <StatusRow ok={!!health.data?.ffmpeg} label={health.data ? (health.data.ffmpeg ? "Ready" : "Missing") : "…"} prefix="Video" />
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-10 py-10">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function StatusRow({ ok, label, prefix }: { ok: boolean; label: string; prefix: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-success" : "bg-warn")} />
      <span>{prefix}</span>
      <span className="ml-auto text-ink/80">{label}</span>
    </div>
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
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 rounded-lg bg-white/5 px-3 py-2.5 text-left ring-1 ring-white/10 transition hover:bg-white/10"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-brand-600 text-xs font-semibold text-white">
          {(current?.name ?? "?").slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{current?.name ?? "Loading…"}</span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1.5 overflow-hidden rounded-lg bg-surface-2 py-1 shadow-panel ring-1 ring-white/10">
          {brands?.map((b) => (
            <button
              key={b.id}
              onClick={() => {
                setOpen(false);
                navigate(`/brands/${b.id}`);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink/90 hover:bg-white/5"
            >
              <span className="flex-1 truncate">{b.name}</span>
              {b.id === currentId && <Check className="h-4 w-4 text-brand-400" />}
            </button>
          ))}
          <div className="my-1 border-t border-line" />
          <button
            onClick={() => {
              setOpen(false);
              navigate("/brands/new");
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted hover:bg-white/5 hover:text-ink"
          >
            <Plus className="h-4 w-4" /> Add brand
          </button>
        </div>
      )}
    </div>
  );
}
