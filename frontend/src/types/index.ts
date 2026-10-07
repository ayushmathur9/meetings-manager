export type UserRole = "admin" | "salesperson";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  active: boolean;
}

export type CompanyStatus =
  | "new"
  | "researched"
  | "contacted"
  | "meeting"
  | "follow_up"
  | "not_interested"
  | "not_a_fit"
  | "existing_customer";

export type VerificationStatus = "unverified" | "needs_review" | "verified" | "failed";
export type LocationSource = "user_provided" | "geocoded" | "verified_business" | "needs_verification";

export interface LocationOut {
  id: string;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  formatted_address: string | null;
  source: LocationSource;
  provider: string | null;
  provider_place_id: string | null;
  confidence: string | null;
  verification_status: VerificationStatus;
  verification_notes: string | null;
  verified_at: string | null;
}

export interface LocationCandidate {
  formatted_address: string;
  latitude: number;
  longitude: number;
  place_id: string | null;
  name: string | null;
  confidence: string;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
}

export interface ContactOut {
  id: string;
  company_id: string;
  first_name: string | null;
  last_name: string | null;
  full_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  contact_type: string;
  verification_status: string;
  source: string | null;
  bigin_contact_id?: string | null;
  crm_deleted_at?: string | null;
}

export interface CompanyListItem {
  id: string;
  name: string;
  industry: string | null;
  phone: string | null;
  status: CompanyStatus;
  is_demo: boolean;
  created_at: string;
}

export interface CompanyOut {
  id: string;
  name: string;
  legal_name: string | null;
  industry: string | null;
  website: string | null;
  phone: string | null;
  email: string | null;
  employee_count: number | null;
  location_count: number | null;
  parent_company: string | null;
  notes: string | null;
  status: CompanyStatus;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
  bigin_account_id?: string | null;
  crm_owner_name?: string | null;
  crm_status?: string | null;
  crm_synced_at?: string | null;
  crm_deleted_at?: string | null;
  locations: LocationOut[];
  contacts: ContactOut[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProspectListItem {
  prospect_id: string | null;
  company_id: string;
  company_name: string;
  industry: string | null;
  phone: string | null;
  status: CompanyStatus;
  employee_count: number | null;
  assigned_user_id: string | null;
  assigned_user_name: string | null;
  priority?: ProspectPriority | null;
  address_line_1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  verification_status: VerificationStatus | null;
  distance_meters: number | null;
  has_contact: boolean;
  contact_count: number;
  next_meeting_date: string | null;
}

export interface ProspectPage {
  items: ProspectListItem[];
  total: number;
  page: number;
  page_size: number;
}

export type MeetingStatus =
  | "scheduled"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "cancelled"
  | "no_show";

export interface MeetingDetail {
  id: string;
  company_id: string;
  contact_id: string | null;
  salesperson_id: string;
  location_id: string | null;
  date: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  status: MeetingStatus;
  notes: string | null;
  next_follow_up_date: string | null;
  company_name: string;
  contact_name: string | null;
  salesperson_name: string;
  address_line_1: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  company_phone: string | null;
  company_website: string | null;
}

export interface NamedLocation {
  name: string;
  address?: string | null;
  latitude: number;
  longitude: number;
}

export interface RouteStopOut {
  id: string;
  meeting_id: string;
  sequence: number;
  arrival_time: string | null;
  departure_time: string | null;
  travel_time_seconds: number | null;
  distance_meters: number | null;
  company_name: string;
  company_id: string;
  address_line_1: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  meeting_status: string;
  contact_name: string | null;
}

export interface RouteOut {
  id: string;
  salesperson_id: string;
  date: string;
  start_location: NamedLocation;
  end_location: NamedLocation | null;
  status: string;
  estimated_distance_meters: number | null;
  estimated_duration_seconds: number | null;
  stops: RouteStopOut[];
}

export interface PlanDaySummary {
  eligible_count: number;
  verified_count: number;
  in_territory_count: number;
  scheduled_count: number;
  excluded_unverified_count: number;
  fixed_meeting_count: number;
  working_hours_end: string;
  last_stop_departure: string | null;
  fits_within_working_hours: boolean;
  available_seconds: number;
}

export interface PlanDayResult {
  route: RouteOut;
  summary: PlanDaySummary;
}

export interface ImportPreview {
  import_id: string;
  columns: string[];
  suggested_mapping: Record<string, string | null>;
  sample_rows: Record<string, string>[];
  row_count: number;
}

export interface ImportOut {
  id: string;
  filename: string;
  column_mapping: Record<string, string> | null;
  row_count: number;
  success_count: number;
  error_count: number;
  duplicate_count: number;
  status: "pending" | "processing" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ImportRowOut {
  id: string;
  row_number: number;
  raw_data: Record<string, string>;
  mapped_data: Record<string, string> | null;
  status: "valid" | "duplicate" | "error" | "imported";
  error_reason: string | null;
  duplicate_of_company_id: string | null;
  created_company_id: string | null;
}

export interface ValidationSummary {
  import_job: ImportOut;
  rows: ImportRowOut[];
}

export interface ImportLocationSummary {
  verified: number;
  needs_review: number;
  unverified: number;
  failed: number;
  total: number;
}

export interface ConfirmImportResult {
  import_job: ImportOut;
  locations: ImportLocationSummary;
}

export interface OrgSettingsOut {
  org_name: string;
  logo_url: string | null;
  default_meeting_duration_minutes: number;
  default_travel_buffer_minutes: number;
  working_hours_start: string;
  working_hours_end: string;
  default_start_location: NamedLocation | null;
  saved_locations: NamedLocation[] | null;
}

// ---------------------------------------------------------------------------
// Sales-day route planner
// ---------------------------------------------------------------------------

export type ProspectPriority = "high" | "medium" | "low";
export type EndMode = "same_as_start" | "custom" | "none";
export type RadiusStatus = "inside" | "outside" | "missing_coordinates";
export type RouteStatus = "draft" | "confirmed" | "in_progress" | "completed";

export interface RoutePlanConfig {
  salesperson_id?: string | null;
  date: string;
  name?: string | null;
  start_location: NamedLocation;
  end_mode: EndMode;
  end_location?: NamedLocation | null;
  working_hours_start: string;
  working_hours_end: string;
  meeting_duration_minutes: number;
  travel_buffer_minutes: number;
  radius_miles: number;
  allow_overtime: boolean;
}

export interface RouteCandidate {
  company_id: string;
  company_name: string;
  industry: string | null;
  status: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  verification_status: string | null;
  priority: ProspectPriority;
  distance_miles: number | null;
  radius_status: RadiusStatus;
  contact_name: string | null;
  phone: string | null;
  assigned_user_id: string | null;
  existing_meeting_id: string | null;
  existing_meeting_time: string | null;
  existing_meeting_fixed: boolean;
}

export interface CandidatesOut {
  radius_miles: number;
  inside_count: number;
  outside_count: number;
  missing_count: number;
  candidates: RouteCandidate[];
}

export interface PlannerStopInput {
  company_id: string;
  duration_minutes?: number | null;
  priority?: ProspectPriority | null;
}

export interface PlannedStop {
  sequence: number;
  company_id: string;
  location_id: string | null;
  meeting_id: string | null;
  meeting_status: string | null;
  company_name: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  priority: ProspectPriority;
  contact_name: string | null;
  phone: string | null;
  duration_minutes: number;
  travel_time_seconds: number;
  distance_meters: number;
  arrival_time: string;
  meeting_start: string;
  meeting_end: string;
  departure_time: string;
  wait_seconds: number;
  late_seconds: number;
  is_fixed_time: boolean;
  outside_hours: boolean;
  outside_radius: boolean;
  location_changed: boolean;
}

export interface UnscheduledStop {
  company_id: string;
  company_name: string;
  priority: ProspectPriority;
  reason: "does_not_fit" | "unreachable" | "missing_coordinates" | "outside_radius";
  message: string;
}

export interface RoutePlan {
  config: RoutePlanConfig;
  stops: PlannedStop[];
  unscheduled: UnscheduledStop[];
  warnings: string[];
  selected_count: number;
  scheduled_count: number;
  day_start: string;
  day_finish: string;
  return_travel_seconds: number;
  return_distance_meters: number;
  total_distance_meters: number;
  total_driving_seconds: number;
  total_meeting_seconds: number;
  total_wait_seconds: number;
  total_duration_seconds: number;
  geometry: number[][][] | null;
  routing_engine: string;
  optimization_engine: string;
}

export interface SavedRoute extends RoutePlan {
  id: string;
  status: RouteStatus;
  salesperson_name: string | null;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
}

export interface RouteListItem {
  id: string;
  name: string | null;
  date: string;
  salesperson_id: string;
  salesperson_name: string | null;
  status: RouteStatus;
  stop_count: number;
  start_name: string | null;
  total_distance_meters: number | null;
  total_driving_seconds: number | null;
  total_duration_seconds: number | null;
  updated_at: string;
}

export interface GeocodeMissingResult {
  company_id: string;
  company_name: string;
  status: "verified" | "already_verified" | "needs_review" | "failed";
  latitude: number | null;
  longitude: number | null;
  message: string | null;
}

// ---------------------------------------------------------------- CRM sync
export type SyncRunStatus = "running" | "success" | "partial" | "failed";

export interface SyncRun {
  id: string;
  trigger: "manual" | "scheduled" | "webhook";
  full: boolean;
  status: SyncRunStatus;
  started_at: string;
  finished_at: string | null;
  companies_created: number;
  companies_updated: number;
  contacts_created: number;
  contacts_updated: number;
  records_deleted: number;
  records_skipped: number;
  addresses_changed: number;
  locations_verified: number;
  locations_needs_review: number;
  message: string | null;
  triggered_by_name: string | null;
}

export interface SyncRunDetail extends SyncRun {
  errors: { module: string; bigin_id: string | null; error: string }[] | null;
}

export interface CrmSyncStatus {
  connection: { configured: boolean; ok: boolean; checked_at: string | null; error: string | null };
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_full_sync_at: string | null;
  last_error: string | null;
  next_sync_at: string | null;
  interval_minutes: number;
  running: SyncRun | null;
  counts: { companies: number; contacts: number; locations: number; needs_review: number; archived: number };
  webhooks: {
    enabled: boolean;
    active: boolean;
    expires_at: string | null;
    last_notification_at: string | null;
    error: string | null;
  };
  recent_runs: SyncRun[];
}

// ------------------------------------------------------- Business overview
export type ResearchStatus = "pending" | "researching" | "summarizing" | "completed" | "failed";

export interface ResearchClaim {
  text: string;
  source_refs: string[];
}

export interface ResearchSummaryData {
  what_they_do: ResearchClaim | null;
  industry: ResearchClaim | null;
  footprint: ResearchClaim[];
  it_relevance: { signal: string; why_it_matters: string; source_refs: string[] }[];
  confidence: "high" | "medium" | "low";
  insufficient_information: boolean;
  caveats: string | null;
}

export interface ResearchSource {
  ref: string;
  source_type: "crm" | "location" | "website";
  url: string | null;
  title: string | null;
  fetched_at: string | null;
}

export interface CompanyResearch {
  status: ResearchStatus | null;
  summary: string | null;
  sam_it_relevance: string | null;
  industry: string | null;
  confidence: string | null;
  summary_data: ResearchSummaryData | null;
  sources: ResearchSource[];
  generated_at: string | null;
  researched_at: string | null;
  is_stale: boolean;
  error: string | null;
  model: string | null;
}

// ------------------------------------------------ Recordings & transcripts
export type RecordingStatus = "uploading" | "processing" | "completed" | "failed";

export interface TranscriptSegment {
  speaker: string;
  start: number;
  end: number;
  text: string;
}

export interface MeetingTranscript {
  id: string;
  provider: string;
  language: string | null;
  text: string;
  segments: TranscriptSegment[] | null;
  speaker_count: number | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface MeetingRecording {
  id: string;
  meeting_id: string;
  status: RecordingStatus;
  content_type: string | null;
  size_bytes: number | null;
  duration_seconds: number | null;
  provider: string | null;
  error: string | null;
  created_at: string;
  uploaded_at: string | null;
  completed_at: string | null;
  created_by_name: string | null;
  can_delete: boolean;
  transcript: MeetingTranscript | null;
}

export interface TranscriptionConfig {
  enabled: boolean;
  provider: string | null;
  max_upload_mb: number;
}

export interface AppConfig {
  quote_builder_url: string | null;
}
