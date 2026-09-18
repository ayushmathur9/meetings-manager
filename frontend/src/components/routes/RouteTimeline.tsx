"use client";

import { ArrowDown, MapPin, Navigation as NavigationIcon, X } from "lucide-react";
import type { RouteOut, RouteStopOut } from "@/types";
import { navigationApi } from "@/lib/api/routes";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

function formatDuration(seconds: number | null) {
  if (!seconds) return null;
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

function formatDistance(meters: number | null) {
  if (!meters) return null;
  return `${(meters / 1609.34).toFixed(1)} mi`;
}

export function RouteTimeline({
  route,
  onRemoveStop,
  selectedStopId,
  onSelectStop,
}: {
  route: RouteOut;
  onRemoveStop?: (stop: RouteStopOut) => void;
  selectedStopId?: string;
  onSelectStop?: (id: string) => void;
}) {
  const toast = useToast();

  async function handleNavigate(lat: number | null, lng: number | null) {
    if (!lat || !lng) return;
    try {
      const { url } = await navigationApi.getLink(lat, lng);
      const win = window.open(url, "_blank");
      if (!win) toast({ title: "Couldn't open navigation", description: "Check your popup blocker.", variant: "error" });
    } catch {
      toast({ title: "Couldn't open navigation", variant: "error" });
    }
  }

  return (
    <div className="space-y-0">
      <div className="flex items-center gap-3 rounded-lg border border-navy-100 bg-navy-50/60 px-4 py-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-900 text-white">
          <MapPin className="h-3.5 w-3.5" />
        </div>
        <p className="text-sm font-medium text-navy-800">Start · {route.start_location.name}</p>
      </div>

      {route.stops.map((stop, i) => {
        const travelTime = formatDuration(stop.travel_time_seconds);
        const travelDistance = formatDistance(stop.distance_meters);
        return (
          <div key={stop.id}>
            <div className="flex items-center gap-3 py-2 pl-4 text-xs text-navy-400">
              <ArrowDown className="h-3.5 w-3.5" />
              {travelTime ? (
                <span>
                  {travelTime}
                  {travelDistance ? ` · ${travelDistance}` : ""} drive
                </span>
              ) : (
                <span>Drive time unavailable</span>
              )}
            </div>
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-500 text-xs font-bold text-white">
                {stop.sequence}
              </div>
              <div
                className={cn(
                  "mb-3 flex-1 cursor-pointer rounded-lg border bg-white p-3.5 shadow-card transition-colors",
                  selectedStopId === stop.meeting_id ? "border-teal-400 ring-2 ring-teal-200" : "border-navy-100"
                )}
                onClick={() => onSelectStop?.(stop.meeting_id)}
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-navy-900">{stop.company_name}</p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-navy-500">{stop.arrival_time?.slice(0, 5)}</span>
                    {onRemoveStop && (
                      <button
                        type="button"
                        title="Remove stop"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRemoveStop(stop);
                        }}
                        className="text-navy-300 hover:text-danger"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-xs text-navy-500">
                  {stop.address_line_1 || "Address pending verification"}
                  {stop.city ? `, ${stop.city}, ${stop.state || ""}` : ""}
                </p>
                {stop.contact_name && <p className="mt-1 text-xs text-navy-400">Contact: {stop.contact_name}</p>}
                <p className="mt-1 text-xs text-navy-400">Meeting until {stop.departure_time?.slice(0, 5)}</p>
                {stop.latitude && stop.longitude && (
                  <Button
                    size="sm"
                    variant="secondary"
                    className="mt-2.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleNavigate(stop.latitude, stop.longitude);
                    }}
                  >
                    <NavigationIcon className="h-3.5 w-3.5" />
                    Navigate
                  </Button>
                )}
              </div>
            </div>
            {i === route.stops.length - 1 && route.end_location && (
              <div className="flex items-center gap-3 pt-1 pl-4 text-xs text-navy-400">
                <ArrowDown className="h-3.5 w-3.5" />
                <span>Return to {route.end_location.name}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
