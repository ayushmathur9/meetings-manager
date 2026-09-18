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
