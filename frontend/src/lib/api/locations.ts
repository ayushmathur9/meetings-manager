import { api } from "@/lib/api/client";
import type { LocationCandidate } from "@/types";

export const locationsApi = {
  search: (q: string) =>
    api.get<{ candidates: LocationCandidate[] }>(`/locations/search?q=${encodeURIComponent(q)}`),
};
