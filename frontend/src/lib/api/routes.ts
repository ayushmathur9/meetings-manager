import { api } from "@/lib/api/client";
import type { CompanyStatus, NamedLocation, PlanDayResult, RouteOut } from "@/types";

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

export const navigationApi = {
  getLink: (destLat: number, destLng: number, originLat?: number, originLng?: number) => {
    const query = new URLSearchParams({ dest_lat: String(destLat), dest_lng: String(destLng) });
    if (originLat !== undefined) query.set("origin_lat", String(originLat));
    if (originLng !== undefined) query.set("origin_lng", String(originLng));
    return api.get<{ url: string }>(`/navigation/link?${query.toString()}`);
  },
};
