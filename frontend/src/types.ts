export interface GenerateFormData {
  product_name: string;
  description: string;
  product_images: File[];
  ref_images: File[];
  logo_images: File[];
  qr_code: File | null;
  enable_rera: boolean;
  rera_number?: string;
}

export type Provider = "gemini" | "openai";

export interface StandaloneGenerateInputs extends GenerateFormData {
  ad_format?: string;
  subtype?: CreativeSubtype;
  count?: number;
  client_id?: string;
  persona_info?: string;
  creative_strategy?: string;
  instructions?: string;
  provider?: Provider;
}

export interface MetaAdCopy {
  primary_text: string | string[];
  headline: string | string[];
  description: string | string[];
  call_to_action: string;
}

export interface PlatformAdCopy {
  meta?: MetaAdCopy;
}

export interface CreativeAdCopy {
  headline?: string;
  body_copy?: string;
  cta?: string;
  platforms: PlatformAdCopy;
}

export interface UploadCreativeInputs {
  subtype: CreativeSubtype;
  name: string;
  client_id?: string;
  campaign_tag?: string;
  primary_text?: string;
  headline?: string;
  description?: string;
  call_to_action?: string;
  files: File[];
}

export type ImageStatus = "pending" | "generating" | "retrying" | "done" | "failed" | "uploaded";
export type ProjectStatus =
  | "pending"
  | "generating_copy"
  | "generating_images"
  | "ready"
  | "failed"
  | "stopped";

export type CreativeSource = "generated" | "uploaded";
export type CreativeType = "image" | "video";
export type CreativeSubtype =
  | "fb-banner"
  | "feed-square"
  | "feed-portrait"
  | "feed-landscape"
  | "story"
  | "logo-square"
  | "logo-rect"
  | "reel"
  | "story-video";

export interface SizeSpecs {
  width: number;
  height: number;
  aspect_ratio: string;
  label: string;
}

export interface CreativeMetadata {
  type: CreativeType;
  subtype: CreativeSubtype;
  size_specs: SizeSpecs;
  platform?: string;
  size_label?: string;
}

export interface GeneratedFields {
  prompt_used: string;
  variation_index: number;
  version: number;
  parent_id: string | null;
  edit_instruction: string | null;
}

export interface UploadedFields {
  original_filename: string;
  mime_type: string;
  campaign_tag: string;
}

export interface Association {
  type: string;  // "project" | "campaign" | "brand" | "client"
  id: string;
}

export interface CreativeOut {
  id: string;
  source: CreativeSource;
  metadata: CreativeMetadata;
  client_id: string;
  associations: Association[];  // replaces project_id
  name: string | null;
  status: ImageStatus;
  s3_key: string;
  creative_url: string | null;
  error_message: string | null;
  generated?: GeneratedFields;
  uploaded?: UploadedFields;
  ad_copy?: CreativeAdCopy;
  created_at: string;
}

export interface JobOut {
  id: string;
  type: string;
  status: string;
  creative_ids: string[];
  creatives: CreativeOut[];
  headline?: string | null;
  body_copy?: string | null;
  generated_cta?: string | null;
  image_prompt?: string | null;
  ad_copy?: CreativeAdCopy | null;
  edit_history?: string[] | null;
  edit_instruction?: string | null;
  created_at: string;
}

export interface AsyncAccepted {
  job_id: string;
}

// Backward-compatibility alias
export type ImageOut = CreativeOut;

export interface GenerationOut {
  headline: string;
  body_copy: string;
  generated_cta: string;
  image_prompt: string;
  ad_copy?: CreativeAdCopy;
  images: ImageOut[];
}

export interface AdSize {
  label: string;
  dimensions: string;
}

export interface PlatformConfig {
  label: string;
  sizes: AdSize[];
}

export const PLATFORM_SIZES: Record<string, PlatformConfig> = {
  meta: {
    label: "Meta (Facebook & Instagram)",
    sizes: [
      { label: "Feed Square", dimensions: "1080x1080" },
      { label: "Feed Portrait", dimensions: "1080x1350" },
      { label: "Feed Landscape", dimensions: "1200x628" },
      { label: "Story / Reels", dimensions: "1080x1920" },
    ],
  },
  google: {
    label: "Google Display Network",
    sizes: [
      { label: "Horizontal",       dimensions: "1200x628" },
      { label: "Square",           dimensions: "600x600" },
      { label: "Logo Square",      dimensions: "1200x1200" },
      { label: "Logo Rectangular", dimensions: "1200x300" },
    ],
  },
};

export interface ProjectOut {
  id: string;
  name: string;
  product_name: string;
  description: string;
  ad_format: string;
  status: ProjectStatus;
  headline: string | null;
  body_copy: string | null;
  generated_cta: string | null;
  image_prompt: string | null;
  error_message: string | null;
  created_at: string;
  images: ImageOut[];
}

export interface EvalCriterion {
  name: string;
  score: number | null;
  notes: string;
}

export interface LogEval {
  criteria: EvalCriterion[];
  overall_notes: string;
}

export interface LogInputs {
  product_name: string;
  description: string;
  ad_format: string;
  has_product_images: boolean;
  has_ref_images: boolean;
}

export interface LogPrompts {
  style_context: string;
  system_prompt: string;
  user_brief: string;
  image_prompt: string;
}

export interface LogAdCopy {
  headline: string;
  body_copy: string;
  cta: string;
}

export interface LogSummary {
  id: string;
  project_id: string;
  project_name: string;
  inputs: LogInputs;
  ad_copy: LogAdCopy;
  eval: LogEval;
  image_count: number;
  created_at: string;
}

export interface LogOut {
  id: string;
  project_id: string;
  project_name: string;
  inputs: LogInputs;
  prompts: LogPrompts;
  ad_copy: LogAdCopy;
  image_ids: string[];
  images: ImageOut[];
  eval: LogEval;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  product_name: string;
  status: string;
  ad_format: string;
  client_id: string;
  created_at: string;
  image_count: number;
  done_count: number;
}

export interface ProjectListResponse {
  items: ProjectSummary[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}
