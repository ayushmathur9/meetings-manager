"use client";

import { useEffect, useMemo, useState } from "react";
import { MapPinned } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { routesApi } from "@/lib/api/routes";
import type { RouteOut } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProspectMap, MapMarkerPoint } from "@/components/map/ProspectMap";
import { RouteTimeline } from "@/components/routes/RouteTimeline";
import { RouteSummary } from "@/components/routes/RouteSummary";
import { LoadingSkeleton } from "@/components/ui/Spinner";

export default function SalesRoutePage() {
  const { user } = useAuth();
  const [route, setRoute] = useState<RouteOut | null | undefined>(undefined);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [selectedStopId, setSelectedStopId] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!user) return;
    routesApi.getByDate(user.id, date).then(setRoute);
  }, [user, date]);

  const markers: MapMarkerPoint[] = route
    ? [
        {
          id: "start",
          lat: route.start_location.latitude,
          lng: route.start_location.longitude,
          label: route.start_location.name,
          status: "assigned",
        },
        ...route.stops
          .filter((s) => s.latitude && s.longitude)
          .map((s) => ({
            id: s.meeting_id,
            lat: s.latitude!,
            lng: s.longitude!,
            label: `${s.sequence}. ${s.company_name}`,
            status: "scheduled" as const,
          })),
      ]
    : [];

  const routeLine = useMemo(() => {
    if (!route) return undefined;
    const points = [{ lat: route.start_location.latitude, lng: route.start_location.longitude }];
    route.stops
      .filter((s) => s.latitude && s.longitude)
      .forEach((s) => points.push({ lat: s.latitude!, lng: s.longitude! }));
    return points.length > 1 ? points : undefined;
  }, [route]);

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-navy-900">My route</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded-lg border border-navy-200 px-3 py-1.5 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
        />
      </div>

      {route === undefined ? (
        <div className="space-y-3">
          <LoadingSkeleton className="h-16 w-full" />
          <LoadingSkeleton className="h-64 w-full" />
        </div>
      ) : route === null || route.stops.length === 0 ? (
        <EmptyState
          icon={<MapPinned className="h-5 w-5" />}
          title="No route created yet"
          description="Select prospects to build today's route, or ask your admin to generate one."
        />
      ) : (
        <div className="flex flex-1 flex-col gap-4 overflow-hidden lg:flex-row">
          <div className="scrollbar-thin flex flex-col gap-4 overflow-y-auto lg:w-1/2">
            <RouteSummary route={route} />
            <RouteTimeline route={route} selectedStopId={selectedStopId} onSelectStop={setSelectedStopId} />
          </div>
          <div className="h-64 shrink-0 lg:h-auto lg:w-1/2">
            <ProspectMap
              markers={markers}
              routeLine={routeLine}
              selectedId={selectedStopId}
              onMarkerClick={setSelectedStopId}
            />
          </div>
        </div>
      )}
    </div>
  );
}
