import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Link2, Unlink } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useToast } from "@/components/toast";
import { Card, Skeleton, Spinner } from "@/components/ui";
import { PLATFORM_META } from "@/components/PostingInsights";
import type { SocialAccount, SocialPlatform } from "@/lib/types";

const HINT: Record<SocialPlatform, string> = {
  linkedin: "linkedin.com/company/yourbrand",
  instagram: "@yourbrand",
  x: "@yourbrand",
};

/** Link the brand's X / LinkedIn / Instagram accounts. Honest: this is a link, not a login. */
export default function ConnectedAccounts({ brandId, compact }: { brandId: number; compact?: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["socials", brandId], queryFn: () => api.listSocials(brandId) });
  const set = (d: SocialAccount[]) => qc.setQueryData(["socials", brandId], d);
  const connect = useMutation({
    mutationFn: (v: { platform: SocialPlatform; value: string }) => api.connectSocial(brandId, v.platform, v.value),
    onSuccess: (d) => { set(d); toast.success("Account linked"); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const disconnect = useMutation({
    mutationFn: (platform: SocialPlatform) => api.disconnectSocial(brandId, platform),
    onSuccess: set,
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Card title="Social accounts">
      {isLoading || !data ? (
        <Skeleton className="h-28" />
      ) : (
        <ul className="space-y-3">
          {data.map((a) => (
            <Row key={a.platform} a={a} busy={connect.isPending || disconnect.isPending}
              onConnect={(value) => connect.mutate({ platform: a.platform, value })}
              onDisconnect={() => disconnect.mutate(a.platform)} />
          ))}
        </ul>
      )}
      {!compact && (
        <p className="mt-4 text-xs leading-relaxed text-muted">
          Linking saves your handle so posts show where they go and open the right profile. AdPilot doesn't log in or post for you: you press Post on the platform. Automatic posting needs each platform's developer-app approval, so it isn't connected.
        </p>
      )}
    </Card>
  );
}

function Row({ a, busy, onConnect, onDisconnect }: { a: SocialAccount; busy: boolean; onConnect: (v: string) => void; onDisconnect: () => void }) {
  const [v, setV] = useState("");
  const { Icon, label } = PLATFORM_META[a.platform];
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="inline-flex w-28 items-center gap-2 text-sm text-ink">
        <Icon className="h-4 w-4" /> {label}
      </span>
      {a.connected ? (
        <>
          <a href={a.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-emerald-300 hover:text-white">
            {a.handle} <ExternalLink className="h-3 w-3" />
          </a>
          <button className="ml-auto inline-flex items-center gap-1 text-xs text-muted hover:text-white" onClick={onDisconnect} disabled={busy}>
            <Unlink className="h-3.5 w-3.5" /> Unlink
          </button>
        </>
      ) : (
        <form className="flex min-w-0 flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); v.trim() && onConnect(v); }}>
          <input className="input h-9 min-w-0 flex-1 text-sm" placeholder={HINT[a.platform]} value={v} onChange={(e) => setV(e.target.value)} aria-label={`${label} handle or link`} />
          <button className="btn-ghost h-9 px-3 text-xs" disabled={busy || !v.trim()}>
            {busy ? <Spinner /> : <Link2 className="h-3.5 w-3.5" />} Link
          </button>
        </form>
      )}
    </li>
  );
}
