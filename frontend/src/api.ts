import axios from "axios";
import { GenerateFormData, ImageOut, LogEval, LogOut, LogSummary, ProjectOut, ProjectSummary, ProjectListResponse, GenerationOut, StandaloneGenerateInputs, UploadCreativeInputs, CreativeOut, JobOut, AsyncAccepted, Provider } from "./types";

const BASE = (import.meta.env.VITE_API_URL || "") + "/api";

axios.defaults.headers.common["X-API-Key"] = import.meta.env.VITE_API_KEY || "";

function _buildGenerateFormData(inputs: StandaloneGenerateInputs): FormData {
  const fd = new FormData();
  fd.append("product_name", inputs.product_name);
  if (inputs.description) fd.append("description", inputs.description);
  if (inputs.ad_format) fd.append("ad_format", inputs.ad_format);
  if (inputs.subtype) fd.append("subtype", inputs.subtype);
  if (inputs.count) fd.append("count", inputs.count.toString());
  if (inputs.client_id) fd.append("client_id", inputs.client_id);
  if (inputs.persona_info) fd.append("persona_info", inputs.persona_info);
  if (inputs.creative_strategy) fd.append("creative_strategy", inputs.creative_strategy);
  if (inputs.instructions) fd.append("instructions", inputs.instructions);
  if (inputs.provider) fd.append("provider", inputs.provider);
  if (inputs.rera_number?.trim()) fd.append("rera_number", inputs.rera_number.trim());
  inputs.product_images.forEach((f) => fd.append("product_images", f));
  inputs.ref_images.forEach((f) => fd.append("ref_images", f));
  inputs.logo_images.forEach((f) => fd.append("logo_images", f));
  if (inputs.qr_code) fd.append("qr_code", inputs.qr_code);
  return fd;
}

export async function standaloneGenerate(inputs: StandaloneGenerateInputs): Promise<AsyncAccepted> {
  const endpoint = `${BASE}/image/generate`;
  const { data } = await axios.post<AsyncAccepted>(endpoint, _buildGenerateFormData(inputs));
  return data;
}


export async function getJob(jobId: string): Promise<JobOut> {
  const { data } = await axios.get<JobOut>(`${BASE}/jobs/${jobId}`);
  return data;
}

export async function uploadStaticCreatives(inputs: UploadCreativeInputs): Promise<ImageOut[]> {
  const fd = new FormData();
  fd.append("subtype", inputs.subtype);
  fd.append("name", inputs.name);
  if (inputs.client_id) fd.append("client_id", inputs.client_id);
  if (inputs.campaign_tag) fd.append("campaign_tag", inputs.campaign_tag);
  if (inputs.primary_text) fd.append("primary_text", inputs.primary_text);
  if (inputs.headline) fd.append("headline", inputs.headline);
  if (inputs.description) fd.append("description", inputs.description);
  if (inputs.call_to_action) fd.append("call_to_action", inputs.call_to_action);

  inputs.files.forEach((f) => fd.append("files", f));

  const { data } = await axios.post<ImageOut[]>(`${BASE}/creatives/upload`, fd);
  return data;
}

export async function createProject(form: GenerateFormData): Promise<ProjectOut> {
  const fd = new FormData();
  fd.append("product_name", form.product_name);
  fd.append("description", form.description);
  fd.append("enable_rera", String(form.enable_rera));
  form.product_images.forEach((f) => fd.append("product_images", f));
  form.ref_images.forEach((f) => fd.append("ref_images", f));
  form.logo_images.forEach((f) => fd.append("logo_images", f));
  if (form.qr_code) fd.append("qr_code", form.qr_code);
  const { data } = await axios.post<ProjectOut>(`${BASE}/projects`, fd);
  return data;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const { data } = await axios.get<ProjectListResponse>(`${BASE}/projects`);
  return data.items;
}

export async function getProject(id: string): Promise<ProjectOut> {
  const { data } = await axios.get<ProjectOut>(`${BASE}/projects/${id}`);
  return data;
}

export async function requestImageEdit(
  imageId: string,
  instruction: string,
  provider?: Provider,
  refImages?: File[]
): Promise<AsyncAccepted> {
  const fd = new FormData();
  fd.append("instruction", instruction);
  if (provider) fd.append("provider", provider);
  if (refImages) refImages.forEach(f => fd.append("ref_images", f));
  const { data } = await axios.post<AsyncAccepted>(`${BASE}/images/${imageId}/edit`, fd);
  return data;
}

export async function requestSizeVariants(
  imageId: string,
  platform: string,
  creativeId?: string,
  sizes?: string[],
  provider?: Provider
): Promise<AsyncAccepted> {
  const { data } = await axios.post<AsyncAccepted>(`${BASE}/images/${imageId}/size-variants`, {
    platform,
    creative_id: creativeId,
    sizes,
    ...(provider ? { provider } : {}),
  });
  return data;
}

export async function batchRegenerate(imageIds: string[], provider?: Provider): Promise<AsyncAccepted> {
  const { data } = await axios.post<AsyncAccepted>(`${BASE}/images/batch-regenerate`, {
    image_ids: imageIds,
    ...(provider ? { provider } : {}),
  });
  return data;
}

export async function getImage(imageId: string): Promise<CreativeOut> {
  const { data } = await axios.get<CreativeOut>(`${BASE}/images/${imageId}`);
  return data;
}

export async function replaceCreativeImage(imageId: string, file: File): Promise<CreativeOut> {
  const fd = new FormData();
  fd.append("file", file);
  const { data } = await axios.post<CreativeOut>(`${BASE}/images/${imageId}/replace`, fd);
  return data;
}

export async function listAllCreatives(
  clientId?: string,
  campaignTag?: string,
  page: number = 1,
  limit: number = 100
): Promise<CreativeOut[]> {
  const { data } = await axios.get<CreativeOut[]>(`${BASE}/creatives/upload`, {
    params: { client_id: clientId, campaign_tag: campaignTag, page, limit }
  });
  return data;
}

export async function listGeneratedCreatives(
  clientId?: string,
  page: number = 1,
  limit: number = 100
): Promise<CreativeOut[]> {
  const { data } = await axios.get<CreativeOut[]>(`${BASE}/images`, {
    params: { client_id: clientId, page, limit }
  });
  return data;
}

export async function stopProject(id: string): Promise<ProjectOut> {
  const { data } = await axios.post<ProjectOut>(`${BASE}/projects/${id}/stop`);
  return data;
}

export async function regenerateProject(id: string): Promise<ProjectOut> {
  const { data } = await axios.post<ProjectOut>(`${BASE}/projects/${id}/regenerate`);
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await axios.delete(`${BASE}/projects/${id}`);
}

export function projectDownloadUrl(projectId: string, platform?: string): string {
  const url = new URL(`${BASE}/projects/${projectId}/download`, window.location.origin);
  if (platform) url.searchParams.set("platform", platform);
  return url.pathname + url.search;
}

export async function listLogs(): Promise<LogSummary[]> {
  const { data } = await axios.get<LogSummary[]>(`${BASE}/logs`);
  return data;
}

export async function getLog(id: string): Promise<LogOut> {
  const { data } = await axios.get<LogOut>(`${BASE}/logs/${id}`);
  return data;
}

export async function updateLogEval(id: string, evalData: LogEval): Promise<LogOut> {
  const { data } = await axios.patch<LogOut>(`${BASE}/logs/${id}/eval`, { eval: evalData });
  return data;
}
