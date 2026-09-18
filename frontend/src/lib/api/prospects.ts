import { api } from "@/lib/api/client";
import type { ProspectPage } from "@/types";

export interface ProspectFilterParams {
  search?: string;
  industry?: string;
  status?: string;
  assigned_user_id?: string;
  unassigned_only?: boolean;
  min_employees?: number;
  max_employees?: number;
  city?: string;
  state?: string;
  postal_code?: string;
  verification_status?: string;
  missing_phone?: boolean;
  missing_website?: boolean;
  missing_contact?: boolean;
  center_lat?: number;
  center_lng?: number;
  radius_miles?: number;
  page?: number;
  page_size?: number;
}

export const prospectsApi = {
  list: (params: ProspectFilterParams = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        query.set(key, String(value));
      }
    });
    return api.get<ProspectPage>(`/prospects?${query.toString()}`);
  },
  bulkAssign: (company_ids: string[], assigned_user_id: string) =>
    api.post<string[]>("/prospects/bulk-assign", { company_ids, assigned_user_id }),
  bulkStatus: (company_ids: string[], status: string) =>
    api.post<{ detail: string }>("/prospects/bulk-status", { company_ids, status }),
  assignSingle: (companyId: string, assignedUserId: string | null) =>
    api.patch<{ detail: string }>(
      `/prospects/${companyId}/assign${assignedUserId ? `?assigned_user_id=${assignedUserId}` : ""}`
    ),
};
