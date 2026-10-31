// Typed client for the AdPilot FastAPI backend (docs/API_CONTRACT.md). Live API only.
import type {
  AnalyzeBrandBody,
  Analytics,
  Asset,
  Brand,
  BrandUpdate,
  Campaign,
  CampaignDetail,
  Concept,
  ConceptUpdate,
  CopyField,
  CreateCampaignBody,
  Health,
  IntegrationStatus,
  Iteration,
  BrandMemoryView,
  Language,
  PostMetrics,
  PostingInsights,
  SocialAccount,
  SocialPlatform,
  SocialPost,
  VideoMode,
  VideoOption,
} from "./types";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** fetch + error mapping. Errors carry the backend's `detail` (status 0 = unreachable). */
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Can't reach the AdPilot API at ${API_URL}.`);
  }
  if (!res.ok) {
    let detail = res.statusText || `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    // FastAPI's bare "Not Found" / "Method Not Allowed" means the route itself doesn't exist yet.
    if ((res.status === 404 && detail === "Not Found") || res.status === 405) {
      detail = "This feature isn't available on the backend yet.";
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

function multipart(fields: Record<string, string | Blob>): RequestInit {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  return { method: "POST", body: fd };
}

/** Backend files are served from /files/...; external image URLs pass through. */
export function fileUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}

export const api = {
  health: () => request<Health>("/api/health"),
  /** FastAPI's route table, so the UI can offer a feature only once the backend has it. */
  routes: async () => (await request<{ paths: Record<string, Record<string, unknown>> }>("/openapi.json")).paths,

  // Brand Intelligence → Brand Memory
  listBrands: () => request<Brand[]>("/api/brands"),
  getBrand: (id: number) => request<Brand>(`/api/brands/${id}`),
  analyzeBrand: (body: AnalyzeBrandBody) => request<Brand>("/api/brands/analyze", json("POST", body)),
  updateBrand: (id: number, patch: BrandUpdate) => request<Brand>(`/api/brands/${id}`, json("PATCH", patch)),
  uploadBrandFile: (id: number, file: File, role: "logo" | "product") =>
    request<Brand>(`/api/brands/${id}/uploads`, multipart({ file, role })),
  deleteBrand: (id: number) => request<void>(`/api/brands/${id}`, { method: "DELETE" }),

  // Strategist + Campaign Management
  listCampaigns: (brandId: number) => request<Campaign[]>(`/api/campaigns?brand_id=${brandId}`),
  createCampaign: (body: CreateCampaignBody) => request<Campaign>("/api/campaigns", json("POST", body)),
  getCampaign: (id: number) => request<CampaignDetail>(`/api/campaigns/${id}`),
  updateCampaign: (id: number, patch: { name?: string; status?: "approved" | "scheduled" }) =>
    request<Campaign>(`/api/campaigns/${id}`, json("PATCH", patch)),
  deleteCampaign: (id: number) => request<void>(`/api/campaigns/${id}`, { method: "DELETE" }),
  async exportCampaign(id: number): Promise<Blob> {
    return (await send(`/api/campaigns/${id}/export`)).blob();
  },

  // Creative Studio
  generateConcepts: (campaignId: number, body: { count?: number; language?: Language } = {}) =>
    request<Concept[]>(`/api/campaigns/${campaignId}/concepts/generate`, json("POST", body)),
  updateConcept: (id: number, patch: ConceptUpdate) => request<Concept>(`/api/concepts/${id}`, json("PATCH", patch)),
  regenerateField: (id: number, field: CopyField) =>
    request<Concept>(`/api/concepts/${id}/regenerate`, json("POST", { field })),
  renderVideo: (conceptId: number, body: { format?: "9:16" | "1:1"; mode?: VideoMode } = {}) =>
    request<Asset>(`/api/concepts/${conceptId}/video`, json("POST", body)),
  videoOptions: (conceptId: number) =>
    request<{ modes: VideoOption[] }>(`/api/concepts/${conceptId}/video-options`),
  uploadAiClip: (conceptId: number, file: File) =>
    request<Asset>(`/api/concepts/${conceptId}/ai-clip`, multipart({ file })),
  removeAiClip: (conceptId: number) => request<void>(`/api/concepts/${conceptId}/ai-clip`, { method: "DELETE" }),

  // Social posts (drafts only; nothing is published)
  generatePosts: (conceptId: number, body: { platforms?: SocialPlatform[]; language?: Language } = {}) =>
    request<SocialPost[]>(`/api/concepts/${conceptId}/posts/generate`, json("POST", body)),
  listPosts: (campaignId: number) => request<SocialPost[]>(`/api/campaigns/${campaignId}/posts`),
  updatePost: (id: number, patch: { text?: string; status?: "generated" | "approved" | "rejected" }) =>
    request<SocialPost>(`/api/posts/${id}`, json("PATCH", patch)),
  regeneratePost: (id: number) => request<SocialPost>(`/api/posts/${id}/regenerate`, json("POST")),
  deletePost: (id: number) => request<void>(`/api/posts/${id}`, { method: "DELETE" }),
  schedulePost: (id: number, scheduledAt: string) =>
    request<SocialPost>(`/api/posts/${id}/schedule`, json("POST", { scheduled_at: scheduledAt })),
  unschedulePost: (id: number) => request<SocialPost>(`/api/posts/${id}/schedule`, { method: "DELETE" }),
  publishPost: (id: number, mode: "manual_share" | "simulated", external_url = "") =>
    request<SocialPost>(`/api/posts/${id}/publish`, json("POST", { mode, external_url })),
  setPostMetrics: (id: number, m: PostMetrics) => request<SocialPost>(`/api/posts/${id}/metrics`, json("POST", m)),
  simulateEngagement: (campaignId: number) =>
    request<{ posts_updated: number; source: "simulated" }>(`/api/campaigns/${campaignId}/posts/simulate-engagement`, json("POST")),
  listSocials: (brandId: number) => request<SocialAccount[]>(`/api/brands/${brandId}/socials`),
  connectSocial: (brandId: number, platform: SocialPlatform, handle_or_url: string) =>
    request<SocialAccount[]>(`/api/brands/${brandId}/socials/${platform}`, json("PUT", { handle_or_url })),
  disconnectSocial: (brandId: number, platform: SocialPlatform) =>
    request<SocialAccount[]>(`/api/brands/${brandId}/socials/${platform}`, { method: "DELETE" }),
  brandPosts: (brandId: number) => request<SocialPost[]>(`/api/brands/${brandId}/posts`),
  postingInsights: (brandId: number) => request<PostingInsights>(`/api/brands/${brandId}/posting-insights`),
  brandMemory: (brandId: number, recall = false) =>
    request<BrandMemoryView>(`/api/brands/${brandId}/memory${recall ? "?recall=true" : ""}`),
  getAsset: (id: number) => request<Asset>(`/api/assets/${id}`),

  // Analytics + Optimization
  simulateMetrics: (campaignId: number, body: { days?: number; seed?: number } = {}) =>
    request<{ rows_saved: number; source_type: "simulated" }>(`/api/campaigns/${campaignId}/metrics/simulate`, json("POST", body)),
  importMetrics: (campaignId: number, file: File) =>
    request<{ rows_saved: number; source_type: "imported_csv"; errors: string[] }>(
      `/api/campaigns/${campaignId}/metrics`,
      multipart({ file }),
    ),
  getAnalytics: (campaignId: number) => request<Analytics>(`/api/campaigns/${campaignId}/analytics`),
  iterate: (campaignId: number, body: { batch_size?: number } = {}) =>
    request<Iteration>(`/api/campaigns/${campaignId}/iterate`, json("POST", body)),

  listIntegrations: () => request<IntegrationStatus[]>("/api/integrations"),
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}
