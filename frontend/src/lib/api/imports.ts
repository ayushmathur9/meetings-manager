import { api } from "@/lib/api/client";
import type { ConfirmImportResult, ImportOut, ImportPreview, ValidationSummary } from "@/types";

export const importsApi = {
  list: () => api.get<ImportOut[]>("/imports"),
  upload: (file: File) => api.upload<ImportPreview>("/imports", file),
  applyMapping: (importId: string, mapping: Record<string, string>) =>
    api.post<ValidationSummary>(`/imports/${importId}/mapping`, { mapping }),
  get: (importId: string) => api.get<ValidationSummary>(`/imports/${importId}`),
  confirm: (importId: string, verifyLocations = true) =>
    api.post<ConfirmImportResult>(`/imports/${importId}/confirm`, { verify_locations: verifyLocations }),
};
