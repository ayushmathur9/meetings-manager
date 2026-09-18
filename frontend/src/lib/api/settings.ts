import { api } from "@/lib/api/client";
import type { NamedLocation, OrgSettingsOut } from "@/types";

export interface OrgSettingsUpdatePayload {
  org_name?: string;
  default_meeting_duration_minutes?: number;
  default_travel_buffer_minutes?: number;
  working_hours_start?: string;
  working_hours_end?: string;
  default_start_location?: NamedLocation | null;
  saved_locations?: NamedLocation[] | null;
}

export const settingsApi = {
  get: () => api.get<OrgSettingsOut>("/settings"),
  update: (payload: OrgSettingsUpdatePayload) => api.patch<OrgSettingsOut>("/settings", payload),
};
