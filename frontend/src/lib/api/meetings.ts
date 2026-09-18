import { api } from "@/lib/api/client";
import type { MeetingDetail } from "@/types";

export interface MeetingCreatePayload {
  company_id: string;
  contact_id?: string | null;
  salesperson_id: string;
  date: string;
  start_time: string;
  duration_minutes?: number;
  notes?: string;
}

export const meetingsApi = {
  list: (params: { salesperson_id?: string; date_from?: string; date_to?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    return api.get<MeetingDetail[]>(`/meetings?${query.toString()}`);
  },
  get: (id: string) => api.get<MeetingDetail>(`/meetings/${id}`),
  create: (payload: MeetingCreatePayload) => api.post<MeetingDetail>("/meetings", payload),
  update: (
    id: string,
    payload: Partial<{
      status: string;
      notes: string;
      date: string;
      start_time: string;
      duration_minutes: number;
      next_follow_up_date: string;
    }>
  ) => api.patch<MeetingDetail>(`/meetings/${id}`, payload),
};
