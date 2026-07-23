/** Typed client for the MSG HRIT backend REST API. */

const API_BASE = ""; // same-origin via Next.js rewrite → backend

/** Default for snappy list/status calls. */
const DEFAULT_TIMEOUT_MS = 8000;
/**
 * Satpy map/globe generation can take well over a minute on first ensure
 * (scene load + resample). Keep polling endpoints short; only heavy POSTs
 * use this budget.
 */
const HEAVY_TIMEOUT_MS = 180_000;

type RequestOptions = RequestInit & { timeoutMs?: number };

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchInit } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchInit,
      signal: fetchInit.signal ?? controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchInit.headers || {}),
      },
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    return res.json() as Promise<T>;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(`Request timed out: ${path}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export type Job = {
  id: number;
  job_type: string;
  scope: string;
  status: string;
  progress_current: number;
  progress_total: number;
  started_at: string | null;
  finished_at: string | null;
  log_summary: string;
};

export type DiskUsageBreakdown = {
  raw_bytes: number;
  processed_bytes: number;
  thumbnails_bytes: number;
  catalog_bytes: number;
  total_bytes: number;
  free_gb: number;
};

export type DashboardStats = {
  discovered_total: number;
  selected_total: number;
  downloaded_total: number;
  failed_downloads: number;
  processed_timeslots: number;
  discovered_bytes: number;
  selected_bytes: number;
  downloaded_bytes_on_disk: number;
  disk_free_gb: number;
  disk_used_data_gb: number;
  disk_breakdown?: DiskUsageBreakdown | null;
  date_min: string | null;
  date_max: string | null;
  active_jobs: Job[];
  config_snapshot: Record<string, unknown>;
  archive_reachable?: boolean | null;
  archive_latency_ms?: number | null;
  archive_check_error?: string | null;
};

export type ConnectivityStatus = {
  reachable: boolean;
  archive_url: string;
  latency_ms: number | null;
  checked_at: string;
  error: string | null;
  http_status: number | null;
};

export type ComparePanel = {
  role: string;
  timeslot: Timeslot | null;
  product: Product | null;
  missing_reason: string | null;
};

export type CompareResponse = {
  date: string;
  product_name: string;
  panels: ComparePanel[];
  available_products: string[];
};

export type DateSummary = {
  date: string;
  year: string;
  discovered_count: number;
  sampled_count: number;
  sample_roles_filled: string[];
  sample_label: string;
  total_bytes: number;
  nearest_fallback_count?: number;
};

export type Timeslot = {
  id: number;
  year: string;
  date: string;
  time: string;
  server_relative_path: string;
  server_reported_size_bytes: number | null;
  sample_role: string | null;
  download_status: string;
  local_raw_path: string | null;
  discovered_at: string;
  downloaded_at: string | null;
  last_error: string | null;
  products_complete?: boolean | null;
  products_generated?: number | null;
  /** Configured target for this role, e.g. "09-00" */
  sample_target_time?: string | null;
  /** within_tolerance | nearest_fallback */
  sample_match?: string | null;
  sample_offset_minutes?: number | null;
  /** Plain-language note for Browse UI */
  sample_note?: string | null;
};

export type ProductReference = {
  product_name: string;
  product_kind: string;
  wavelength_or_spectral_band: string;
  approximate_resolution: string;
  plain_language_description: string;
  agriculture_application: string;
  aviation_application: string;
  natural_resource_application: string;
  disaster_response_application: string;
};

export type Product = {
  id: number;
  timeslot_id: number;
  product_name: string;
  product_kind: string;
  availability_status: string;
  local_image_path: string | null;
  local_thumbnail_path: string | null;
  generated_at: string | null;
  error_message: string | null;
  image_url?: string | null;
  thumbnail_url?: string | null;
  map_image_url?: string | null;
  has_map_overlay?: boolean;
  reference?: ProductReference | null;
};

export type MapViewConfig = {
  crs: string;
  projection: string;
  west: number;
  south: number;
  east: number;
  north: number;
  center_lat: number;
  center_lon: number;
  default_zoom: number;
  leaflet_bounds: [[number, number], [number, number]];
};

export type MapEnsureResult = {
  ok: boolean;
  product_id: number;
  status: "ready" | "generating" | "error" | "busy" | "unavailable" | string;
  map_image_url?: string | null;
  error?: string | null;
};

export type GlobeBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
  semantics: string;
};

export type GlobeMetadata = {
  version: string;
  product: string;
  bounds: GlobeBounds;
  dimensions: {
    width: number;
    height: number;
  };
};

export type GlobeGenerationStatus =
  | "not_generated"
  | "generating"
  | "ready"
  | "unavailable_night"
  | "error"
  | "busy"
  | "ineligible";

export type GlobeProduct = {
  product_id: number;
  timeslot_id: number;
  product_name: string;
  product_kind: string;
  availability_status: string;
  generation_status: GlobeGenerationStatus;
  image_url: string | null;
  metadata: GlobeMetadata | null;
  error: string | null;
  reference: ProductReference | null;
};

export type GlobeCatalog = {
  timeslot_id: number;
  products: GlobeProduct[];
};

export type FinalGlobeItem = {
  timeslot_id: number;
  date: string;
  time: string;
  sample_role: string | null;
  sample_note?: string | null;
  status: "generated" | "missing" | "error" | string;
  product_id?: number | null;
  image_url?: string | null;
  thumbnail_url?: string | null;
  error_message?: string | null;
  source_limit?: number;
};

export type FinalGlobeListResponse = {
  product_name: string;
  product_label: string;
  description: string;
  source_limit: number;
  total: number;
  generated_count: number;
  items: FinalGlobeItem[];
  generate_running: boolean;
};

export type ActionResult = {
  ok: boolean;
  job_id?: number | null;
  job_type?: string | null;
  error?: string | null;
};

export const api = {
  health: () => request<{ status: string; db_ok: boolean }>("/api/health"),
  connectivity: () => request<ConnectivityStatus>("/api/connectivity"),
  dashboard: () => request<DashboardStats>("/api/dashboard"),
  diskUsage: (refresh = true) =>
    request<DiskUsageBreakdown>(`/api/disk-usage?refresh=${refresh ? "true" : "false"}`),
  dates: () => request<DateSummary[]>("/api/browse/dates"),
  compare: (date: string, product: string) =>
    request<CompareResponse>(
      `/api/compare?date=${encodeURIComponent(date)}&product=${encodeURIComponent(product)}`
    ),
  mapView: () => request<MapViewConfig>("/api/map-view"),
  ensureMapImage: (productId: number) =>
    request<MapEnsureResult>(`/api/map-images/${productId}/ensure`, {
      method: "POST",
      // Non-blocking enqueue — keep short so navigation stays responsive.
      timeoutMs: DEFAULT_TIMEOUT_MS,
    }),
  mapImageStatus: (productId: number) =>
    request<MapEnsureResult>(`/api/map-images/${productId}/status`),
  timeslots: (params: Record<string, string | boolean | number> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => q.set(k, String(v)));
    return request<Timeslot[]>(`/api/timeslots?${q}`);
  },
  timeslot: (id: number) =>
    request<{
      timeslot: Timeslot;
      products: Product[];
      siblings: Timeslot[];
    }>(`/api/timeslots/${id}`),
  globeCatalog: (timeslotId: number) =>
    request<GlobeCatalog>(`/api/timeslots/${timeslotId}/globe-products`),
  generateGlobeProduct: (productId: number) =>
    request<GlobeProduct>(`/api/globe-products/${productId}/generate`, {
      method: "POST",
      timeoutMs: HEAVY_TIMEOUT_MS,
    }),
  globeProductStatus: (productId: number) =>
    request<GlobeProduct>(`/api/globe-products/${productId}/status`),
  reference: () => request<ProductReference[]>("/api/reference"),
  jobs: () => request<Job[]>("/api/jobs"),
  discoveryStatus: () => request<Record<string, unknown>>("/api/discovery/status"),
  samplingStatus: () => request<Record<string, unknown>>("/api/sampling/status"),
  downloadStatus: () => request<Record<string, unknown>>("/api/download/status"),
  processingStatus: () => request<Record<string, unknown>>("/api/processing/status"),
  pipelineStatus: () => request<Record<string, unknown>>("/api/pipeline/status"),
  finalGlobes: () => request<FinalGlobeListResponse>("/api/final-globes"),
  finalGlobeStatus: () =>
    request<Record<string, unknown>>("/api/final-globes/status"),
  generateFinalGlobes: (force = false) =>
    request<ActionResult>(`/api/final-globes/generate?force=${force}`, {
      method: "POST",
    }),
  generateFinalGlobe: (timeslotId: number, force = false) =>
    request<ActionResult>(
      `/api/final-globes/${timeslotId}/generate?force=${force}`,
      { method: "POST" }
    ),

  runDiscovery: () =>
    request<ActionResult>("/api/discovery/run", { method: "POST" }),
  runSampling: () =>
    request<ActionResult>("/api/sampling/run", { method: "POST" }),
  startDownload: () =>
    request<ActionResult>("/api/download/start", { method: "POST" }),
  pauseDownload: () =>
    request<ActionResult>("/api/download/pause", { method: "POST" }),
  startProcessing: () =>
    request<ActionResult>("/api/processing/start", { method: "POST" }),
  pauseProcessing: () =>
    request<ActionResult>("/api/processing/pause", { method: "POST" }),
  startPipeline: () =>
    request<ActionResult>("/api/pipeline/start", { method: "POST" }),
  pausePipeline: () =>
    request<ActionResult>("/api/pipeline/pause", { method: "POST" }),
  retryDownload: (id: number) =>
    request<ActionResult>(`/api/timeslots/${id}/retry-download`, {
      method: "POST",
    }),
  retryProcessing: (id: number) =>
    request<ActionResult>(`/api/timeslots/${id}/retry-processing`, {
      method: "POST",
    }),
};

export function formatBytes(n: number): string {
  if (!n || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 2)} ${units[i]}`;
}
