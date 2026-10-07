import { api } from "@/lib/api/client";
import type {
  CandidatesOut,
  CompanyStatus,
  GeocodeMissingResult,
  NamedLocation,
  PlanDayResult,
  PlannerStopInput,
  RouteListItem,
  RouteOut,
  RoutePlan,
  RoutePlanConfig,
  RouteStatus,
  SavedRoute,
} from "@/types";

export interface GenerateRoutePayload {
  salesperson_id: string;
  date: string;
  start_location: NamedLocation;
  end_location?: NamedLocation | null;
  working_hours_start?: string;
  working_hours_end?: string;
  meeting_duration_minutes?: number;
  travel_buffer_minutes?: number;
  meeting_ids: string[];
}

export interface PlanDayPayload {
  salesperson_id: string;
  date: string;
  start_location: NamedLocation;
  end_location?: NamedLocation | null;
  working_hours_start?: string;
  working_hours_end?: string;
  meeting_duration_minutes?: number;
  travel_buffer_minutes?: number;
  target_meetings?: number;
  radius_miles?: number;
  industry?: string | null;
  status?: CompanyStatus | null;
  include_unverified?: boolean;
}

export const routesApi = {
  generate: (payload: GenerateRoutePayload) => api.post<RouteOut>("/routes/generate", payload),
  plan: (payload: PlanDayPayload) => api.post<PlanDayResult>("/routes/plan", payload),
  getByDate: (salesperson_id: string, date: string) =>
    api.get<RouteOut | null>(`/routes/by-date?salesperson_id=${salesperson_id}&date=${date}`),
  reorder: (routeId: string, ordered_meeting_ids: string[]) =>
    api.patch<RouteOut>(`/routes/${routeId}/reorder`, { ordered_meeting_ids }),
};

export interface CandidatesPayload {
  salesperson_id?: string | null;
  date?: string;
  start_location: NamedLocation;
  radius_miles: number;
  search?: string;
  scope?: "assigned" | "all";
}

export interface OptimizePayload extends RoutePlanConfig {
  stops: PlannerStopInput[];
  optimize: boolean;
}

/** Sales-day planner endpoints (Geoapify-backed, via our backend only). */
export const routePlannerApi = {
  preview: (payload: CandidatesPayload) => api.post<CandidatesOut>("/routes/preview", payload),
  optimize: (payload: OptimizePayload) => api.post<RoutePlan>("/routes/optimize", payload),
  geocodeMissing: (company_ids: string[]) =>
    api.post<GeocodeMissingResult[]>("/routes/geocode-missing", { company_ids }),
  list: (params: { salesperson_id?: string; date_from?: string; date_to?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v && query.set(k, v));
    return api.get<RouteListItem[]>(`/routes?${query.toString()}`);
  },
  get: (routeId: string) => api.get<SavedRoute>(`/routes/${routeId}`),
  save: (plan: RoutePlan, status?: RouteStatus) => api.post<SavedRoute>("/routes", { plan, status }),
  update: (routeId: string, payload: { plan?: RoutePlan; name?: string; status?: RouteStatus }) =>
    api.patch<SavedRoute>(`/routes/${routeId}`, payload),
  remove: (routeId: string) => api.delete<void>(`/routes/${routeId}`),
  recalculate: (routeId: string, optimize = false) =>
    api.post<RoutePlan>(`/routes/${routeId}/recalculate`, { optimize }),
};

export const navigationApi = {
  getLink: (destLat: number, destLng: number, originLat?: number, originLng?: number) => {
    const query = new URLSearchParams({ dest_lat: String(destLat), dest_lng: String(destLng) });
    if (originLat !== undefined) query.set("origin_lat", String(originLat));
    if (originLng !== undefined) query.set("origin_lng", String(originLng));
    return api.get<{ url: string }>(`/navigation/link?${query.toString()}`);
  },
};
