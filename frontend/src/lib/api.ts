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
  Language,
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
  return (res.status === 204 ? undefined : await res.json()) as T;
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

  // Brand Intelligence → Brand Memory
  listBrands: () => request<Brand[]>("/api/brands"),
  getBrand: (id: number) => request<Brand>(`/api/brands/${id}`),
  analyzeBrand: (body: AnalyzeBrandBody) => request<Brand>("/api/brands/analyze", json("POST", body)),
  updateBrand: (id: number, patch: BrandUpdate) => request<Brand>(`/api/brands/${id}`, json("PATCH", patch)),
  uploadBrandFile: (id: number, file: File, role: "logo" | "product") =>
    request<Brand>(`/api/brands/${id}/uploads`, multipart({ file, role })),

  // Strategist + Campaign Management
  listCampaigns: (brandId: number) => request<Campaign[]>(`/api/campaigns?brand_id=${brandId}`),
  createCampaign: (body: CreateCampaignBody) => request<Campaign>("/api/campaigns", json("POST", body)),
  getCampaign: (id: number) => request<CampaignDetail>(`/api/campaigns/${id}`),
  updateCampaign: (id: number, patch: { name?: string; status?: "approved" | "scheduled" }) =>
    request<Campaign>(`/api/campaigns/${id}`, json("PATCH", patch)),
  async exportCampaign(id: number): Promise<Blob> {
    return (await send(`/api/campaigns/${id}/export`)).blob();
  },

  // Creative Studio
  generateConcepts: (campaignId: number, body: { count?: number; language?: Language } = {}) =>
    request<Concept[]>(`/api/campaigns/${campaignId}/concepts/generate`, json("POST", body)),
  updateConcept: (id: number, patch: ConceptUpdate) => request<Concept>(`/api/concepts/${id}`, json("PATCH", patch)),
  regenerateField: (id: number, field: CopyField) =>
    request<Concept>(`/api/concepts/${id}/regenerate`, json("POST", { field })),
  renderVideo: (conceptId: number, body: { format?: "9:16" | "1:1" } = {}) =>
    request<Asset>(`/api/concepts/${conceptId}/video`, json("POST", body)),
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
