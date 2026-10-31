# API Contract: frontend ↔ backend

Keep this file in step with the code: update it first when an endpoint or type changes.
Base URL: `VITE_API_URL` (default `http://localhost:8000`). All bodies are JSON unless marked `multipart`. Files are served from `GET /files/<path>`.

## Conventions
- IDs are integers. Timestamps are ISO-8601 UTC strings.
- Errors: `{ "detail": string }` with a 4xx/5xx status. **The UI only shows success on a 2xx.**
- Every AI-produced object carries `generation_mode`: `"gemini" | "offline"`. Assets carry `"template" | "template+ai_broll" | "template+tts"`.
- Every metric row and analytics response carries its data provenance (`source_type` / `data_sources` / `is_simulated`).
- Nullable numbers (`null`) mean **undefined** (e.g. CTR with 0 impressions). Render them as "—", never as 0.

## TypeScript types (copy into `frontend/src/lib/types.ts`)

```ts
export type GenerationMode = "gemini" | "offline";
export type CampaignStatus = "draft" | "generated" | "approved" | "scheduled" | "published" | "failed";
export type ConceptStatus = "generated" | "approved" | "rejected";
export type AssetStatus = "queued" | "rendering" | "ready" | "failed";
export type Objective = "awareness" | "traffic" | "leads" | "sales" | "engagement" | "launch";
export type ConceptType = "problem" | "demo" | "storytelling" | "offer" | "testimonial-style";
export type SourceType = "simulated" | "imported_csv" | `api:${string}`;
export type SampleStatus = "insufficient_data" | "early_signal" | "directional";

export interface AudienceHypothesis { segment: string; need: string; evidence: string; confidence: "low" | "medium" | "high"; }
export interface ApprovedClaim { claim: string; source: string; }
export interface ProductInfo { name: string; description: string; price: string | null; image_url: string | null; features: string[]; }

export interface BrandProfile {
  brand_name: string; product_name: string; product_category: string; description: string;
  products: ProductInfo[];
  value_propositions: string[]; features: string[];
  audience_hypotheses: AudienceHypothesis[];
  brand_tone: string[]; differentiators: string[];
  approved_claims: ApprovedClaim[];
  unknowns_to_confirm: string[];
  visual_identity: { primary?: string; secondary?: string; accent?: string; style?: string[] };
  source_urls: string[];
}

export interface Brand {
  id: number; name: string; website: string;
  profile: BrandProfile;
  guardrails: { claims_to_avoid?: string[]; words_to_avoid?: string[]; notes?: string };
  learnings: { text: string; iteration_id: number; data_source: SourceType; created_at: string }[];
  sources: { id: string; text: string; url: string }[];
  warnings: string[];
  logo_url: string | null;
  product_image_urls: string[];
  generation_mode: GenerationMode;
  created_at: string; updated_at: string;
}

export interface CampaignStrategy {
  objective: Objective; positioning_statement: string; primary_kpi: string;
  segments: { name: string; pain_points: string[]; message: string }[];
  campaign_themes: string[]; creative_angles: string[];
  channel_plan: { channel: string; role: string; formats: string[] }[];
  ctas: string[];
  content_calendar: { day: number; channel: string; content: string; concept_type: string }[];
  assumptions: string[]; not_claimed: string[];
}

export interface VisualBrief { scene: string; composition: string; product_placement: string; text_safe_area: string; style: string; layout: "hero" | "split" | "minimal" | "bold"; }
export interface VideoBeat { beat: "hook" | "product" | "benefit" | "cta"; seconds: number; on_screen_text: string; voiceover: string; }
export interface RiskFlag { code: string; message: string; severity: "info" | "warn" | "block"; field?: string; }

export interface PlatformCopy {
  instagram?: { caption: string; hashtags: string[] };
  meta_ads?: { primary_text: string; headline: string; description: string; cta: string };
  google_ads?: { headlines: string[]; descriptions: string[] };   // ≤30 / ≤90 chars
}

export interface Concept {
  id: number; campaign_id: number; iteration_id: number | null; parent_concept_id: number | null;
  concept_type: ConceptType; target_segment: string; angle: string;
  hook: string; primary_text: string; headline: string; cta: string;
  visual_brief: VisualBrief; platform_copy: PlatformCopy; video_script: VideoBeat[];
  claim_sources: string[]; risk_flags: RiskFlag[];
  changed_variables: string[]; rationale: string; is_exploration: boolean;
  status: ConceptStatus; edited: boolean;
  generation_mode: GenerationMode; prompt_version: string;
  latest_video: Asset | null;
  created_at: string; updated_at: string;
}

export interface Asset {
  id: number; campaign_id: number; concept_id: number | null; brand_id: number | null;
  kind: "video" | "image" | "upload"; fmt: string;
  url: string | null;            // /files/... when ready
  status: AssetStatus; progress: number;   // 0..1
  generation_mode: string; error: string;
  meta: { duration_s?: number; width?: number; height?: number; render_ms?: number };
  created_at: string; updated_at: string;
}

export interface Campaign {
  id: number; brand_id: number; name: string; objective: Objective; channels: string[];
  product_focus: string; audience_note: string; budget_note: string;
  status: CampaignStatus; strategy: CampaignStrategy; generation_mode: GenerationMode;
  counts: { concepts: number; approved: number; videos_ready: number };
  created_at: string; updated_at: string;
}

export interface CampaignDetail { campaign: Campaign; concepts: Concept[]; assets: Asset[]; iterations: Iteration[]; has_metrics: boolean; }

export interface ConceptPerformance {
  concept_id: number; label: string; concept_type: ConceptType; is_exploration: boolean;
  impressions: number; clicks: number; conversions: number; spend: number; revenue: number | null;
  ctr: number | null; cvr: number | null; cpc: number | null; cpa: number | null; roas: number | null;
  primary_value: number | null; ci_low: number | null; ci_high: number | null;
  sample_status: SampleStatus; p_best: number | null;
  rank: number; hook: string; parent_concept_id: number | null;   // added in G3
}

export interface Analytics {
  campaign_id: number; objective: Objective; objective_metric: "ctr" | "cvr"; objective_metric_note: string;
  clear_winner: boolean;   // true only if the leader's 95% interval clears the runner-up's
  is_simulated: boolean; data_sources: SourceType[];
  totals: Omit<ConceptPerformance, "concept_id" | "label" | "concept_type" | "is_exploration" | "primary_value" | "ci_low" | "ci_high" | "sample_status" | "p_best">;
  by_concept: ConceptPerformance[];
  daily: { day: string; impressions: number; clicks: number; conversions: number; spend: number }[];
  warnings: string[];
}

export interface Iteration {
  id: number; campaign_id: number; objective_metric: string;
  insight_summary: string;
  ranking: { concept_id: number; rank: number; primary_value: number | null; p_best: number | null; sample_status: SampleStatus }[];
  selected_signals: { concept_id: number; signal: string }[];
  limitations: string[]; data_sources: SourceType[];
  variants: Concept[];              // the new concepts created by this iteration
  generation_mode: GenerationMode; created_at: string;
}

export interface IntegrationStatus { provider: string; label: string; status: "working" | "export_only" | "simulated" | "not_connected"; notes: string; docs_url: string; }
```

## Endpoints

| Method & path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/health` | — | `{ status: "ok" \| "degraded", database: boolean, llm_provider: string, providers: { name, configured, model, ready, paused_for_s, reason }[], ffmpeg: boolean, demo_store_url: string }` | `llm_provider` = the provider that would answer next (`gemini`, `groq`, `openrouter`, `mistral`, `cerebras`, `ollama`, `custom`, or `offline`). `generation_mode` on any AI output is that same name, so render unknown names as plain text. |
| `POST /api/brands/analyze` | `{ url?: string, manual?: { brand_name?, product_name?, product_description?, target_audience?, price_range?, tone?, key_features?: string[], claims_to_avoid?: string[] } }` | `Brand` | 5–25 s. Needs URL **or** manual brand_name. 422 on invalid URL, 400 with `detail` if extraction fails *and* there's no manual data. |
| `GET /api/brands` | — | `Brand[]` | |
| `GET /api/brands/{id}` | — | `Brand` | |
| `PATCH /api/brands/{id}` | `{ name?, profile?: BrandProfile, guardrails? }` | `Brand` | Brand Memory editing |
| `POST /api/brands/{id}/uploads` | multipart `file`, `role: "logo" \| "product"` | `Asset` | png/jpg/webp, ≤10 MB |
| `POST /api/campaigns` | `{ brand_id, name?, objective, channels: string[], product_focus?, audience_note?, budget_note? }` | `Campaign` (status `generated`, with strategy) | 5–20 s |
| `GET /api/campaigns?brand_id=` | — | `Campaign[]` | |
| `GET /api/campaigns/{id}` | — | `CampaignDetail` | |
| `PATCH /api/campaigns/{id}` | `{ name?, strategy?, status?: "approved" \| "scheduled" }` | `Campaign` | `approved` requires ≥1 approved concept (409 otherwise) |
| `POST /api/campaigns/{id}/concepts/generate` | `{ count?: 5, language?: "en" \| "hi" \| "hinglish" }` | `Concept[]` | Adds to the campaign |
| `PATCH /api/concepts/{id}` | `{ status?, hook?, primary_text?, headline?, cta?, target_segment? }` | `Concept` | Copy edits re-run the claim guard → updated `risk_flags` |
| `POST /api/concepts/{id}/regenerate` | `{ field: "hook" \| "headline" \| "cta" \| "primary_text" }` | `Concept` | |
| `POST /api/concepts/{id}/video` | `{ format?: "9:16" \| "1:1", mode?: "motion" \| "ai_clip" }` | `Asset` (202, `queued`) | Poll `GET /api/assets/{id}` every 1.5 s. `ai_clip` = **Pro** mode: 409 unless a clip is attached. Default `motion` is the standard video. |
| `GET /api/concepts/{id}/video-options` | — | `{ modes: { mode, label, tier: "standard" \| "pro", available, has_clip?, description, needs? }[] }` | Drives the "Standard / Pro - AI video" choice |
| `POST /api/concepts/{id}/ai-clip` | multipart `file` (mp4/mov/webm, ≤80 MB, ≤30 s) | `Asset` (`kind: "ai_clip"`) | Attach an AI-generated clip for Pro mode |
| `DELETE /api/concepts/{id}/ai-clip` | — | 204 | Remove clips; Standard keeps working |
| `GET /api/concepts/{id}/ai-prompt` | — | `{ prompt, duration_s, ... }` | Optional: text to paste into an AI video tool |
| `POST /api/concepts/{id}/posts/generate` | `{ platforms?: ("linkedin" \| "instagram" \| "x")[], language?: "en" \| "hi" \| "hinglish" }` | `SocialPost[]` | Replaces un-approved drafts for the same concept + platform |
| `GET /api/campaigns/{id}/posts` | — | `SocialPost[]` | |
| `PATCH /api/posts/{id}` | `{ text?, status?: "generated" \| "approved" \| "rejected" }` | `SocialPost` | Editing re-runs the claim guard; approving with a `block` flag (or an X post over 280) returns 409 |
| `POST /api/posts/{id}/regenerate` | — | `SocialPost` | A different take for the same platform |
| `DELETE /api/posts/{id}` | — | 204 | |
| `POST /api/posts/{id}/schedule` | `{ scheduled_at: ISO datetime }` | `SocialPost` | Needs status `approved` or `scheduled`; 409 otherwise. `DELETE` on the same path unschedules |
| `POST /api/posts/{id}/publish` | `{ mode?: "manual_share" \| "simulated", external_url?: string }` | `SocialPost` | Records that the post went out. Nothing is posted by AdPilot: `manual_share` means the user pressed Post on the platform |
| `POST /api/posts/{id}/metrics` | `{ impressions, likes, comments, shares, clicks }` | `SocialPost` | 409 unless published; stored as `metrics_source: "manual"` |
| `POST /api/campaigns/{id}/posts/simulate-engagement` | — | `SocialPost[]` | Labelled `simulated`; for demos |
| `GET /api/brands/{id}/posts` | — | `SocialPost[]` | All posts across the brand's campaigns |
| `GET /api/brands/{id}/posting-insights` | — | `PostingInsights` | Best slots per platform (IST), heatmap, content patterns, plain-language `preferences`, `next_slots` |
| `GET /api/brands/{id}/memory?recall=false` | — | `BrandMemoryView` | What is stored in Meko (counts, status, datapack id). `recall=true` runs a live Meko search (a few seconds) |
| `GET /api/brands/{id}/socials` | — | `SocialAccount[]` | One row per platform |
| `PUT /api/brands/{id}/socials/{platform}` | `{ handle_or_url }` | `SocialAccount[]` | Validates the handle or profile link, 422 with a message otherwise. A link, not a login |
| `DELETE /api/brands/{id}/socials/{platform}` | — | `SocialAccount[]` | |
| `GET /api/concepts/{id}/video-options` | — | `{ modes: VideoOption[] }` | Standard vs Pro (AI clip) |
| `GET /api/assets/{id}` | — | `Asset` | |
| `GET /api/assets?brand_id=&kind=` | — | `Asset[]` | Asset library |
| `GET /api/campaigns/{id}/export` | — | `application/zip` | Approved concepts only. 409 if none. |
| `POST /api/campaigns/{id}/metrics/simulate` | `{ days?: 7, seed?: 42 }` | `{ rows_saved: number, source_type: "simulated" }` | Replaces previous simulated rows |
| `POST /api/campaigns/{id}/metrics` | multipart `file` (CSV) | `{ rows_saved, source_type: "imported_csv", errors: string[] }` | CSV columns: `concept_id,day,platform,impressions,clicks,conversions,spend,revenue` |
| `GET /api/campaigns/{id}/analytics` | — | `Analytics` | |
| `POST /api/campaigns/{id}/iterate` | `{ batch_size?: 4 }` | `Iteration` | 409 if no metrics |
| `GET /api/integrations` | — | `IntegrationStatus[]` | |

### SocialPost

```ts
type SocialPost = {
  id: number; campaign_id: number; concept_id: number;
  platform: "linkedin" | "instagram" | "x";
  hook: string;                 // first line
  text: string;                 // ready to paste: body + hashtags
  hashtags: string[]; thread: string[];   // thread: X only, 3 follow-ups
  visual_idea: string; cta: string;
  risk_flags: RiskFlag[];       // same shape as concept flags
  status: "generated" | "approved" | "rejected" | "scheduled" | "published"; edited: boolean;
  generation_mode: string;      // "offline" or the AI provider name
  scheduled_at: string | null; published_at: string | null;
  publish_mode: "" | "manual_share" | "simulated" | "synthetic_history";
  external_url: string;
  metrics: { impressions: number; likes: number; comments: number; shares: number; clicks: number };
  metrics_source: "" | "manual" | "simulated" | "synthetic_history";
  engagement_rate: number | null;   // (likes + 2*comments + 3*shares + clicks) / impressions
  suggested?: { at: string; label: string; reason: string } | null;   // best next slot for this platform
  char_count: number; char_limit: number;   // X: links count as 23; show "412 / 3000"
};
```

Nothing is published by AdPilot: publishing is `manual_share` (the user presses Post on the platform) or `simulated` (labelled). Approved posts are included in the campaign export (`social_posts.json` and `social_posts/*.txt`).

### SocialAccount

```ts
type SocialAccount = {
  platform: "linkedin" | "instagram" | "x"; label: string;
  connected: boolean; handle: string; url: string; connected_at: string | null;
  publishing: "manual_share";   // always: we link accounts, we do not log in or post
  note: string;
};
```

## Mocks
`sample_data/fixtures/` holds **real** responses captured from the backend (`brand.json`, `campaign_detail.json`, `analytics.json`, `iteration.json`, `integrations.json`, `asset_ready.json`, plus `video.mp4`).
Also available: `analytics.json`, `iteration.json`, `asset_ready.json`, plus `../backup_video.mp4` for the mock video player and `../sample_metrics.csv` for the CSV upload screen (concept ids 1–5).
Iteration `generation_mode` can be `rules+gemini` or `rules+offline` (the ranking and plan are rules; only rewritten copy uses the LLM).
