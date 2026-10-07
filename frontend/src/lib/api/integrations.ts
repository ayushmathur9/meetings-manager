import { api, ApiError, API_BASE_URL } from "@/lib/api/client";
import type {
  AppConfig,
  CompanyResearch,
  CrmSyncStatus,
  MeetingRecording,
  SyncRun,
  SyncRunDetail,
  TranscriptionConfig,
} from "@/types";

export const crmSyncApi = {
  status: () => api.get<CrmSyncStatus>("/crm-sync/status"),
  run: (full = false) => api.post<SyncRun>("/crm-sync/run", { full }),
  runs: (limit = 50) => api.get<SyncRun[]>(`/crm-sync/runs?limit=${limit}`),
  run_detail: (id: string) => api.get<SyncRunDetail>(`/crm-sync/runs/${id}`),
};

export const researchApi = {
  get: (companyId: string) => api.get<CompanyResearch>(`/companies/${companyId}/research`),
  refresh: (companyId: string) => api.post<CompanyResearch>(`/companies/${companyId}/research/refresh`),
};

export const appConfigApi = {
  get: () => api.get<AppConfig>("/app-config"),
};

export const recordingsApi = {
  config: () => api.get<TranscriptionConfig>("/recordings/config"),
  list: (meetingId: string) => api.get<MeetingRecording[]>(`/meetings/${meetingId}/recordings`),
  retry: (id: string) => api.post<MeetingRecording>(`/recordings/${id}/retry`),
  remove: (id: string) => api.delete<void>(`/recordings/${id}`),
  /** Same-origin-credentialed URL; the API redirects to a short-lived signed URL or streams the file. */
  audioUrl: (id: string) => `${API_BASE_URL}/recordings/${id}/audio`,
  transcriptUrl: (id: string) => `${API_BASE_URL}/recordings/${id}/transcript.txt`,

  /** Upload with progress (fetch can't report upload progress). */
  upload: (
    meetingId: string,
    blob: Blob,
    durationSeconds: number,
    onProgress?: (fraction: number) => void
  ): Promise<MeetingRecording> =>
    new Promise((resolve, reject) => {
      const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
      const form = new FormData();
      form.append("file", blob, `meeting.${ext}`);
      form.append("duration_seconds", durationSeconds.toFixed(1));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE_URL}/meetings/${meetingId}/recordings`);
      xhr.withCredentials = true;
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total);
      };
      xhr.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          // non-JSON error page
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as MeetingRecording);
        } else {
          const detail = (body as { detail?: unknown } | null)?.detail;
          reject(new ApiError(xhr.status, typeof detail === "string" ? detail : "Upload failed"));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error while uploading the recording"));
      xhr.send(form);
    }),

  /** Download via the authenticated API (cookies) and hand the file to the browser. */
  downloadTranscript: async (id: string) => {
    const res = await fetch(recordingsApi.transcriptUrl(id), { credentials: "include" });
    if (!res.ok) throw new ApiError(res.status, "Couldn't download the transcript");
    const disposition = res.headers.get("content-disposition") || "";
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] || "transcript.txt";
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};
