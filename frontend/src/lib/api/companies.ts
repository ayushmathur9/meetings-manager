import { api } from "@/lib/api/client";
import type { CompanyOut, Page, CompanyListItem, LocationCandidate } from "@/types";

export interface CompanyCreatePayload {
  name: string;
  industry?: string;
  website?: string;
  phone?: string;
  email?: string;
  employee_count?: number;
  notes?: string;
  address_line_1?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
}

export const companiesApi = {
  list: (params: { search?: string; page?: number; page_size?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    return api.get<Page<CompanyListItem>>(`/companies?${query.toString()}`);
  },
  get: (id: string) => api.get<CompanyOut>(`/companies/${id}`),
  create: (payload: CompanyCreatePayload) => api.post<CompanyOut>("/companies", payload),
  update: (id: string, payload: Partial<CompanyCreatePayload> & { status?: string }) =>
    api.patch<CompanyOut>(`/companies/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/companies/${id}`),
  getLocationCandidates: (id: string) =>
    api.get<{ candidates: LocationCandidate[] }>(`/companies/${id}/location/candidates`),
  resolveLocation: (id: string, candidate: LocationCandidate) =>
    api.post<CompanyOut>(`/companies/${id}/location/resolve`, { candidate }),
};
