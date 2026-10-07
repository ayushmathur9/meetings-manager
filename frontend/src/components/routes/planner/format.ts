import type { ProspectPriority } from "@/types";

const METERS_PER_MILE = 1609.344;

/** "08:38:00" -> "8:38 AM" */
export function formatClock(value: string | null | undefined): string {
  if (!value) return "—";
  const [h, m] = value.split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")} ${suffix}`;
}

/** 3900 -> "1 hr 5 min" */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

export function formatMiles(meters: number | null | undefined, digits = 1): string {
  if (meters == null) return "—";
  return `${(meters / METERS_PER_MILE).toFixed(digits)} mi`;
}

/** "2026-10-12" -> "Mon, Oct 12, 2026" (no timezone shifting) */
export function formatDate(value: string): string {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export const PRIORITY_STYLES: Record<ProspectPriority, { label: string; className: string }> = {
  high: { label: "High", className: "bg-red-50 text-danger ring-red-200" },
  medium: { label: "Medium", className: "bg-amber-50 text-warning ring-amber-200" },
  low: { label: "Low", className: "bg-navy-50 text-navy-500 ring-navy-200" },
};

/** Opens turn-by-turn navigation in the user's maps app (Google Maps deep link). */
export function navigationUrl(lat: number, lng: number): string {
  const params = new URLSearchParams({ api: "1", destination: `${lat},${lng}`, travelmode: "driving" });
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}
