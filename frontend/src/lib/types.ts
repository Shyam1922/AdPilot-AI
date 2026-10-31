// Copied from docs/API_CONTRACT.md — the frozen frontend ↔ backend handshake.

export type GenerationMode = "gemini" | "offline";
export type CampaignStatus =
  | "draft"
  | "generated"
  | "approved"
  | "scheduled"
  | "published"
  | "failed";
export type ConceptStatus = "generated" | "approved" | "rejected";
export type AssetStatus = "queued" | "rendering" | "ready" | "failed";
export type Objective =
  | "awareness"
  | "traffic"
  | "leads"
  | "sales"
  | "engagement"
  | "launch";
export type ConceptType =
  | "problem"
  | "demo"
  | "storytelling"
  | "offer"
  | "testimonial-style";
export type SourceType = "simulated" | "imported_csv" | `api:${string}`;
export type SampleStatus = "insufficient_data" | "early_signal" | "directional";

export interface AudienceHypothesis {
  segment: string;
  need: string;
  evidence: string;
  confidence: "low" | "medium" | "high";
}
export interface ApprovedClaim {
  claim: string;
  source: string;
}
export interface ProductInfo {
  name: string;
  description: string;
  price: string | null;
  image_url: string | null;
  features: string[];
}

export interface BrandProfile {
  brand_name: string;
  product_name: string;
  product_category: string;
  description: string;
  products: ProductInfo[];
  value_propositions: string[];
  features: string[];
  audience_hypotheses: AudienceHypothesis[];
  brand_tone: string[];
  differentiators: string[];
  approved_claims: ApprovedClaim[];
  unknowns_to_confirm: string[];
  visual_identity: {
    primary?: string;
    secondary?: string;
    accent?: string;
    style?: string[];
  };
  source_urls: string[];
}

export interface Brand {
  id: number;
  name: string;
  website: string;
  profile: BrandProfile;
  guardrails: {
    claims_to_avoid?: string[];
    words_to_avoid?: string[];
    notes?: string;
  };
  learnings: {
    text: string;
    iteration_id: number;
    data_source: SourceType;
    created_at: string;
  }[];
  sources: { id: string; text: string; url: string }[];
  warnings: string[];
  logo_url: string | null;
  product_image_urls: string[];
  generation_mode: GenerationMode;
  created_at: string;
  updated_at: string;
}

export interface CampaignStrategy {
  objective: Objective;
  positioning_statement: string;
  primary_kpi: string;
  segments: { name: string; pain_points: string[]; message: string }[];
  campaign_themes: string[];
  creative_angles: string[];
  channel_plan: { channel: string; role: string; formats: string[] }[];
  ctas: string[];
  content_calendar: {
    day: number;
    channel: string;
    content: string;
    concept_type: string;
  }[];
  assumptions: string[];
  not_claimed: string[];
}

export interface VisualBrief {
  scene: string;
  composition: string;
  product_placement: string;
  text_safe_area: string;
  style: string;
  layout: "hero" | "split" | "minimal" | "bold";
}
export interface VideoBeat {
  beat: "hook" | "product" | "benefit" | "cta";
  seconds: number;
  on_screen_text: string;
  voiceover: string;
}
export interface RiskFlag {
  code: string;
  message: string;
  severity: "info" | "warn" | "block";
  field?: string;
}

export interface PlatformCopy {
  instagram?: { caption: string; hashtags: string[] };
  meta_ads?: {
    primary_text: string;
    headline: string;
    description: string;
    cta: string;
  };
  google_ads?: { headlines: string[]; descriptions: string[] };
}

export interface Concept {
  id: number;
  campaign_id: number;
  iteration_id: number | null;
  parent_concept_id: number | null;
  concept_type: ConceptType;
  target_segment: string;
  angle: string;
  hook: string;
  primary_text: string;
  headline: string;
  cta: string;
  visual_brief: VisualBrief;
  platform_copy: PlatformCopy;
  video_script: VideoBeat[];
  claim_sources: string[];
  risk_flags: RiskFlag[];
  changed_variables: string[];
  rationale: string;
  is_exploration: boolean;
  status: ConceptStatus;
  edited: boolean;
  generation_mode: GenerationMode;
  prompt_version: string;
  latest_video: Asset | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: number;
  campaign_id: number;
  concept_id: number | null;
  brand_id: number | null;
  kind: "video" | "image" | "upload";
  fmt: string;
  url: string | null;
  status: AssetStatus;
  progress: number;
  generation_mode: string;
  error: string;
  meta: {
    duration_s?: number;
    width?: number;
    height?: number;
    render_ms?: number;
  };
  created_at: string;
  updated_at: string;
}

export interface Campaign {
  id: number;
  brand_id: number;
  name: string;
  objective: Objective;
  channels: string[];
  product_focus: string;
  audience_note: string;
  budget_note: string;
  status: CampaignStatus;
  strategy: CampaignStrategy;
  generation_mode: GenerationMode;
  counts: { concepts: number; approved: number; videos_ready: number };
  created_at: string;
  updated_at: string;
}

export interface CampaignDetail {
  campaign: Campaign;
  concepts: Concept[];
  assets: Asset[];
  iterations: Iteration[];
  has_metrics: boolean;
}

export interface ConceptPerformance {
  concept_id: number;
  label: string;
  concept_type: ConceptType;
  is_exploration: boolean;
  impressions: number;
  clicks: number;
  conversions: number;
  spend: number;
  revenue: number | null;
  ctr: number | null;
  cvr: number | null;
  cpc: number | null;
  cpa: number | null;
  roas: number | null;
  primary_value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  sample_status: SampleStatus;
  p_best: number | null;
}

export interface Analytics {
  campaign_id: number;
  objective_metric: "ctr" | "cvr" | "roas";
  objective_metric_note: string;
  is_simulated: boolean;
  data_sources: SourceType[];
  totals: Omit<
    ConceptPerformance,
    | "concept_id"
    | "label"
    | "concept_type"
    | "is_exploration"
    | "primary_value"
    | "ci_low"
    | "ci_high"
    | "sample_status"
    | "p_best"
  >;
  by_concept: ConceptPerformance[];
  daily: {
    day: string;
    impressions: number;
    clicks: number;
    conversions: number;
    spend: number;
  }[];
  warnings: string[];
}

export interface Iteration {
  id: number;
  campaign_id: number;
  objective_metric: string;
  insight_summary: string;
  ranking: {
    concept_id: number;
    rank: number;
    primary_value: number | null;
    p_best: number | null;
    sample_status: SampleStatus;
  }[];
  selected_signals: { concept_id: number; signal: string }[];
  limitations: string[];
  data_sources: SourceType[];
  variants: Concept[];
  generation_mode: GenerationMode;
  created_at: string;
}

export interface IntegrationStatus {
  provider: string;
  label: string;
  status: "working" | "export_only" | "simulated" | "not_connected";
  notes: string;
  docs_url: string;
}

export interface Health {
  status: "ok";
  llm_provider: GenerationMode;
  ffmpeg: boolean;
  demo_store_url: string;
}

/* ---- request bodies (mirror backend/app/schemas) ---- */

export interface ManualBrandInput {
  brand_name?: string;
  product_name?: string;
  product_description?: string;
  target_audience?: string;
  price_range?: string;
  tone?: string;
  key_features?: string[];
  claims_to_avoid?: string[];
}

export interface AnalyzeBrandBody {
  url?: string;
  manual?: ManualBrandInput;
}

export interface BrandUpdate {
  name?: string;
  profile?: BrandProfile;
  guardrails?: Brand["guardrails"];
}

export interface CreateCampaignBody {
  brand_id: number;
  name?: string;
  objective: Objective;
  channels: string[];
  product_focus?: string;
  audience_note?: string;
  budget_note?: string;
}

export type Language = "en" | "hi" | "hinglish";
export type CopyField = "hook" | "headline" | "cta" | "primary_text";

export interface ConceptUpdate {
  status?: ConceptStatus;
  hook?: string;
  primary_text?: string;
  headline?: string;
  cta?: string;
  target_segment?: string;
}
