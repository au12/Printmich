export type Intent = 'perceptual' | 'relative' | 'saturation' | 'absolute'
export type Sharpening = 'off' | 'low' | 'standard' | 'high'

export interface Adjustments {
  brightness: number
  contrast: number
  saturation: number
  cyan: number
  magenta: number
  yellow: number
  shadows: number
  highlights: number
}

export interface Tone {
  preset: 'neutral' | 'cool' | 'warm' | 'custom'
  x: number
  y: number
}

export interface ColorSettings {
  mode: 'color' | 'bw' | 'bw-toned'
  space: 'auto' | 'srgb' | 'adobe-rgb'
  intent: 'paper' | Intent
  bpc: boolean
  management: 'managed' | 'custom-icc' | 'passthrough'
  icc_profile: string | null
  tone: Tone
  send_rendering_intent: boolean
}

export interface Margins {
  top: number
  right: number
  bottom: number
  left: number
}

export interface Caption {
  enabled: boolean
  template: string
  font: 'serif' | 'sans' | 'mono'
  size_pt: number
  color: string
  align: 'left' | 'center' | 'right'
  italic: boolean
  letter_spacing: number
}

export interface Layout {
  borderless: boolean
  margins: Margins
  fit: 'fill' | 'fit'
  crop: 'smart' | 'faces' | 'attention' | 'center'
  orientation: 'auto' | 'portrait' | 'landscape'
  keyline: boolean
  keyline_color: string
  keyline_width_pt: number
  border_color: string
  caption: Caption
}

export interface OutputSettings {
  paper_id: string
  media_size: string
  media_source: string
  media_type: string
  quality: 'high' | 'normal' | 'draft'
  resolution: number
  document_format: 'auto' | 'pwg' | 'jpeg'
  bit_depth: 8 | 16
  copies: number
  sharpening: 'paper' | Sharpening
  extra_ipp: Record<string, string | number | boolean>
}

export interface Preset {
  id: string
  name: string
  description: string
  output: OutputSettings
  layout: Layout
  color: ColorSettings
  adjust: Adjustments
  sort: number
  created_at?: string | null
  updated_at?: string | null
  size_label?: string
  paper_name?: string
}

export interface PaperCalibration {
  intent: Intent
  bpc: boolean
  sharpening: Sharpening
  adjust: Adjustments
  notes: string
  calibrated_at: string | null
}

export interface Paper {
  id: string
  name: string
  brand: string
  code: string
  finish: string
  weight_gsm: number | null
  black_ink: 'photo' | 'matte'
  feeds: ('top' | 'manual')[]
  default_feed: 'top' | 'manual'
  borderless: boolean
  recommended_margins: Margins | null
  media_type_hints: string[]
  media_type_generic: string[]
  media_type: string
  calibration: PaperCalibration
  cost_per_sheet: Record<string, number>
  sizes: string[]
  notes: string
  tint: string
  sheen: number
  builtin: boolean
  customized: boolean
  resolved?: {
    media_type: { keyword: string | null; label: string; how: string }
    media_source: string | null
    media_source_label: string | null
  } | null
  size_labels?: Record<string, string>
}

export interface AssetSummary {
  id: string
  filename: string
  taken_at: string | null
  width: number | null
  height: number | null
  mime: string
  favorite: boolean
  rating: number | null
  city: string | null
  state: string | null
  country: string | null
  description: string | null
  make: string | null
  model: string | null
  lens: string | null
  f_number: number | null
  exposure_time: string | null
  iso: number | null
  focal_length: number | null
  latitude: number | null
  longitude: number | null
  people: string[]
  thumbhash: string | null
  edited: boolean
  owner: string | null
  printed?: boolean
  printed_count?: number
}

export type SourceKind =
  | 'favorites' | 'album' | 'person' | 'tag' | 'on_this_day' | 'memories' | 'smart' | 'rating' | 'recent' | 'random'

export interface SourceSpec {
  id: string
  kind: SourceKind
  weight: number
  album_ids: string[]
  person_ids: string[]
  person_mode: 'any' | 'all'
  tag_ids: string[]
  query: string
  min_rating: number
  recent_days: number
  window_days: number
  favorites_only: boolean
  label: string
}

export interface PickFilters {
  include_archived: boolean
  taken_after: string | null
  taken_before: string | null
  min_ppi: number
  orientation: 'any' | 'landscape' | 'portrait'
  exclude_screenshots: boolean
  avoid_repeats_days: number
  exclude_album_ids: string[]
  require_people: boolean
  smart_pick: boolean
  candidates: number
  skip_blurry: boolean
}

export interface Timing {
  frequency: 'daily' | 'weekly' | 'monthly' | 'every_n_days' | 'cron'
  time: string
  weekdays: number[]
  day_of_month: number
  every_n_days: number
  cron: string
}

export interface Pick {
  id: string
  schedule_id: string
  asset_id: string
  asset: AssetSummary
  score: {
    total: number | null
    components: Record<string, number>
    ppi?: number | null
    crop?: number | null
    pool?: number
    considered?: number
  }
  source: string
  status: 'pending' | 'approved' | 'skipped' | 'printing' | 'printed' | 'expired' | 'swapped'
  due_at: string | null
  created_at: string
  print_id: string | null
}

export interface Schedule {
  id: string
  name: string
  enabled: boolean
  preset_id: string
  timing: Timing
  sources: SourceSpec[]
  filters: PickFilters
  approval: { mode: 'auto' | 'preview' | 'manual'; lead_hours: number }
  verify_paper: boolean
  catch_up_hours: number
  notify: { on_pick: boolean; on_print: boolean; on_error: boolean }
  next_run_at: string | null
  last_run_at: string | null
  timing_text?: string
  upcoming_runs?: string[]
  pick?: Pick | null
  preset_name?: string | null
  last_print?: PrintItem | null
  print_count?: number
}

export interface PlanInfo {
  kind: 'pwg' | 'jpeg'
  document_format: string
  dpi: number
  bits: number
  space: 'srgb' | 'adobe-rgb' | 'sgray'
  page_keyword: string
  page_w_mm: number
  page_h_mm: number
  page_label: string
  borderless: boolean
  media_type: string | null
  media_type_label: string
  media_type_how: string
  media_source: string | null
  media_source_label: string
  quality: string
  color_mode_ipp: string | null
  rendering_intent_ipp: string | null
  intent: string
  copies: number
  copies_ipp: boolean
  hw_margins: Margins
  warnings: string[]
  summary: string
}

export interface PrintItem {
  id: string
  status: 'queued' | 'preparing' | 'rendering' | 'sending' | 'printing' | 'waiting' | 'held' | 'completed' | 'failed' | 'canceled'
  detail: string
  error: string | null
  source: 'manual' | 'schedule' | 'reprint' | 'test'
  created_at: string
  started_at: string | null
  completed_at: string | null
  asset: AssetSummary | null
  asset_id: string | null
  schedule_id: string | null
  pick_id: string | null
  preset_id: string | null
  preset_name: string | null
  paper: { id: string; name: string; code: string; finish: string; brand: string; tint: string }
  media_size: string
  size_label: string
  borderless: boolean
  plan: Partial<PlanInfo>
  geometry: Record<string, unknown> | null
  effective_ppi: number | null
  crop: Record<string, unknown> | null
  notes: string[]
  copies: number
  cost: number | null
  ink: Record<string, number> | null
  ipp_job_id: number | null
  hidden: boolean
  thumb: string | null
  page: string | null
  thumb_w: number | null
  thumb_h: number | null
}

export interface Marker {
  name: string
  color: string
  level: number
  low: number
  high: number
  type: string
}

export interface InkTank {
  ink: string
  name: string
  color: string
  capacity_ml: number
  level_ml: number | null
  percent: number | null
  since: string | null
  since_kind?: 'refill' | 'set'
  used_ml: number
  prints: number
  days: number | null
  status: 'ok' | 'low' | 'empty' | 'unknown'
  factor: number
  calibrations: number
}

export interface InkSettings {
  levels: 'printer' | 'estimate'
  tank_ml: number
  remind_below: number
  hold_below: number
  remind_days: number
  hide_printer_warnings: boolean
}

export interface InkEvent {
  id: number
  at: string
  ink: string
  kind: 'refill' | 'set'
  level_ml: number | null
  level_before_ml: number | null
  added_ml: number | null
  used_ml: number | null
  used_est_ml: number | null
  note: string | null
}

export interface InkState {
  settings: InkSettings
  tanks: InkTank[]
  events: InkEvent[]
  printer: Marker[]
  inks: { ink: string; name: string; color: string }[]
}

export interface PrinterStatus {
  configured: boolean
  online?: boolean
  state?: string
  reasons?: { keyword: string; base: string; severity: string; text: string; hint?: string }[]
  ink?: { mode: 'estimate'; tanks: InkTank[]; tracking: boolean }
  message?: string
  markers?: Marker[]
  ready?: {
    source: string | null
    source_label: string | null
    size: string | null
    size_label: string | null
    type: string | null
    type_label: string | null
  }[]
  error?: string
}

export interface MediaSizeCap {
  keyword: string
  label: string
  width_mm: number
  height_mm: number
  borderless: boolean
  sources: string[]
}

export interface Capabilities {
  uri: string
  make_model: string
  name: string
  info: string
  location: string
  firmware: string
  admin_url: string
  state: string
  formats: string[]
  pwg_resolutions: number[]
  pwg_types: string[]
  urf: string[]
  sizes: MediaSizeCap[]
  types: { keyword: string; label: string }[]
  sources: { keyword: string; label: string }[]
  qualities: string[]
  resolutions: number[]
  color_modes: string[]
  rendering_intents: string[]
  copies_max: number
  hw_margins: Margins
  borderless_capable: boolean
  markers: Marker[]
  virtual: boolean
}

export interface PrinterInfo {
  configured: boolean
  uri?: string
  virtual?: boolean
  capabilities?: Capabilities
  status?: PrinterStatus
  icon?: boolean
  error?: string
}

export interface ImmichCheck {
  ok: boolean
  error: string | null
  version: string
  key_name: string | null
  full_access: boolean
  read_only: boolean | null
  user: { name: string; email: string } | null
  permissions: Record<'required' | 'recommended' | 'writeback', { name: string; why: string; granted: boolean | null }[]>
  features: { smart_search: boolean; facial_recognition: boolean }
  album_search: boolean
}

export interface Settings {
  immich_url: string
  immich_public_url: string
  immich_api_key_set: boolean
  immich_api_key_hint: string
  printer_uri: string
  printer_name: string
  units: 'in' | 'mm'
  theme: 'auto' | 'dark' | 'light'
  notifications: {
    urls: string[]
    on_pick: boolean
    on_print: boolean
    on_error: boolean
    on_supplies: boolean
    attach_preview: boolean
  }
  writeback: { album_enabled: boolean; album_name: string; tag_enabled: boolean; tag_name: string }
  cost: { currency: string; ink_per_sq_in: number; ink_per_ml: number }
  ink: InkSettings
  retry_minutes: number
  retry_hours: number
  onboarded: boolean
  wall_title: string
  env_locked: string[]
  api_token_set: boolean
  password_set: boolean
  timezone: string
  public_url: string | null
  demo: boolean
}

export interface Stats {
  total: number
  sheets: number
  this_month: number
  cost: number
  since: string | null
  by_paper: { name: string; n: number; sheets: number }[]
  by_size: { size: string; n: number }[]
  streak: number
  years: string[]
}

export interface EventItem {
  id: number
  ts: string
  level: 'info' | 'success' | 'warning' | 'error'
  kind: string
  message: string
  data: Record<string, unknown> | null
}

export interface DashboardSchedule {
  id: string
  name: string
  enabled: boolean
  next_run_at: string | null
  timing_text: string
  approval: 'auto' | 'preview' | 'manual'
  preset_id: string
  preset_name: string | null
  pick: Pick | null
}

export interface Dashboard {
  upcoming: DashboardSchedule | null
  schedules: DashboardSchedule[]
  queue: PrintItem[]
  recent: PrintItem[]
  printer: PrinterStatus
  stats: Stats
  events: EventItem[]
  checklist: { key: string; label: string; done: boolean }[]
}

export interface AppStatus {
  version: string
  immich: boolean
  printer: boolean
  virtual_printer: boolean
  onboarded: boolean
  demo: boolean
  timezone: string
  units: 'in' | 'mm'
  theme: 'auto' | 'dark' | 'light'
  wall_title: string
  immich_public_url: string
}

export interface RenderInfo {
  plan: PlanInfo
  geometry: {
    page_mm: [number, number]
    layout_mm: [number, number]
    landscape: boolean
    rotated: boolean
    margins_mm: Margins
    photo_mm: [number, number]
    photo_px: [number, number]
    photo_offset_px: [number, number]
    dpi: number
    caption: boolean
  }
  crop: { x: number; y: number; w: number; h: number; focus: [number, number]; method: string }
  warnings: string[]
  caption: string
  effective_ppi: number | null
  tiles?: { index: number; label: string; adjust: Adjustments }[]
}

export interface Album {
  id: string
  name: string
  count: number
  thumbnail: string | null
  shared: boolean
  start: string | null
  end: string | null
}

export interface Person {
  id: string
  name: string
  favorite: boolean
  hidden: boolean
}
