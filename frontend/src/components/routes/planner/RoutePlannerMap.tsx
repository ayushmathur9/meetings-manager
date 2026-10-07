"use client";

import "mapbox-gl/dist/mapbox-gl.css";
import Map, { Layer, Marker, NavigationControl, Popup, Source, type MapRef } from "react-map-gl/mapbox";
import { useEffect, useMemo, useRef } from "react";
import { Flag, Home, MapPin, Navigation as NavigationIcon } from "lucide-react";
import type { NamedLocation, PlannedStop, RouteCandidate } from "@/types";
import { cn } from "@/lib/utils";
import { formatClock, navigationUrl } from "./format";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN || "";
const HAS_REAL_TOKEN = MAPBOX_TOKEN && MAPBOX_TOKEN !== "REPLACE_WITH_REAL_TOKEN";

type LngLat = [number, number];

function circlePolygon(center: NamedLocation, radiusMiles: number): LngLat[] {
  const points: LngLat[] = [];
  const latRadius = radiusMiles / 69.0;
  const lngRadius = radiusMiles / (69.172 * Math.cos((center.latitude * Math.PI) / 180));
  for (let i = 0; i <= 64; i++) {
    const angle = (i / 64) * 2 * Math.PI;
    points.push([center.longitude + lngRadius * Math.cos(angle), center.latitude + latRadius * Math.sin(angle)]);
  }
  return points;
}

export function RoutePlannerMap({
  start,
  end,
  endIsStart,
  stops,
  candidates,
  selectedIds,
  geometry,
  radiusMiles,
  activeCompanyId,
  onSelectCompany,
  onOpenDetails,
  stale,
}: {
  start: NamedLocation | null;
  end: NamedLocation | null;
  endIsStart: boolean;
  stops: PlannedStop[];
  candidates: RouteCandidate[];
  selectedIds: Set<string>;
  geometry: number[][][] | null;
  radiusMiles: number;
  activeCompanyId: string | null;
  onSelectCompany: (companyId: string | null) => void;
  onOpenDetails: (companyId: string) => void;
  stale?: boolean;
}) {
  const mapRef = useRef<MapRef>(null);
  const stopIds = useMemo(() => new Set(stops.map((s) => s.company_id)), [stops]);

  const routeFeature = useMemo(() => {
    if (geometry && geometry.length) {
      return { type: "Feature" as const, properties: {}, geometry: { type: "MultiLineString" as const, coordinates: geometry } };
    }
    // No road geometry (e.g. routing provider without geometry): a dashed
    // straight-line sketch so the visiting order is still visible.
    if (!start || stops.length === 0) return null;
    const coords: LngLat[] = [[start.longitude, start.latitude]];
    stops.forEach((s) => s.latitude != null && s.longitude != null && coords.push([s.longitude, s.latitude]));
    if (end) coords.push([end.longitude, end.latitude]);
    return { type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: coords } };
  }, [geometry, start, end, stops]);

  const radiusFeature = useMemo(() => {
    if (!start || !radiusMiles) return null;
    return {
      type: "Feature" as const,
      properties: {},
      geometry: { type: "Polygon" as const, coordinates: [circlePolygon(start, radiusMiles)] },
    };
  }, [start, radiusMiles]);

  // Fit to the full route whenever it changes; otherwise to the radius area.
  const boundsKey = useMemo(() => {
    const parts = [start?.latitude, start?.longitude, radiusMiles, stops.map((s) => s.company_id).join(","), geometry ? geometry.length : 0];
    return parts.join("|");
  }, [start, radiusMiles, stops, geometry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !start) return;
    const coords: LngLat[] = [[start.longitude, start.latitude]];
    if (end) coords.push([end.longitude, end.latitude]);
    if (stops.length) {
      stops.forEach((s) => s.latitude != null && s.longitude != null && coords.push([s.longitude, s.latitude]));
      geometry?.forEach((line) => line.forEach((p) => coords.push([p[0], p[1]])));
    } else if (radiusFeature) {
      radiusFeature.geometry.coordinates[0].forEach((p) => coords.push(p));
    }
    const lngs = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    const bounds: [LngLat, LngLat] = [
      [Math.min(...lngs), Math.min(...lats)],
      [Math.max(...lngs), Math.max(...lats)],
    ];
    if (bounds[0][0] === bounds[1][0] && bounds[0][1] === bounds[1][1]) {
      map.flyTo({ center: bounds[0], zoom: 12, duration: 500 });
    } else {
      map.fitBounds(bounds, { padding: 56, duration: 600, maxZoom: 14 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundsKey]);

  const activeStop = stops.find((s) => s.company_id === activeCompanyId) ?? null;
  const activeCandidate = !activeStop ? candidates.find((c) => c.company_id === activeCompanyId) ?? null : null;

  if (!HAS_REAL_TOKEN) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-navy-200 bg-navy-50 p-8 text-center">
        <MapPin className="h-5 w-5 text-navy-400" />
        <p className="text-sm font-medium text-navy-700">Map preview unavailable</p>
        <p className="max-w-xs text-xs text-navy-500">
          Set NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN to show the map. Planning, schedules and navigation still work.
        </p>
      </div>
    );
  }

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={MAPBOX_TOKEN}
      initialViewState={{
        longitude: start?.longitude ?? -77.9155,
        latitude: start?.latitude ?? 35.7213,
        zoom: 11,
      }}
      style={{ width: "100%", height: "100%", borderRadius: "0.75rem" }}
      mapStyle="mapbox://styles/mapbox/light-v11"
      onClick={() => onSelectCompany(null)}
    >
      <NavigationControl position="top-right" showCompass={false} />

      {radiusFeature && (
        <Source id="planner-radius" type="geojson" data={radiusFeature}>
          <Layer id="planner-radius-fill" type="fill" paint={{ "fill-color": "#26a69c", "fill-opacity": 0.04 }} />
          <Layer
            id="planner-radius-line"
            type="line"
            paint={{ "line-color": "#26a69c", "line-width": 1, "line-opacity": 0.5, "line-dasharray": [2, 2] }}
          />
        </Source>
      )}

      {routeFeature && (
        <Source id="planner-route" type="geojson" data={routeFeature}>
          <Layer
            id="planner-route-casing"
            type="line"
            layout={{ "line-join": "round", "line-cap": "round" }}
            paint={{ "line-color": "#ffffff", "line-width": 7, "line-opacity": stale ? 0.4 : 0.9 }}
          />
          <Layer
            id="planner-route-line"
            type="line"
            layout={{ "line-join": "round", "line-cap": "round" }}
            paint={{
              "line-color": "#1b847d",
              "line-width": 4,
              "line-opacity": stale ? 0.35 : 0.95,
              ...(geometry && geometry.length ? {} : { "line-dasharray": [1, 1.5] }),
            }}
          />
        </Source>
      )}

      {/* Prospects not on the route */}
      {candidates
        .filter((c) => c.latitude != null && c.longitude != null && !stopIds.has(c.company_id))
        .map((c) => {
          const selected = selectedIds.has(c.company_id);
          return (
            <Marker
              key={`cand-${c.company_id}`}
              longitude={c.longitude!}
              latitude={c.latitude!}
              onClick={(e) => {
                e.originalEvent.stopPropagation();
                onSelectCompany(c.company_id);
              }}
            >
              <div
                title={c.company_name}
                className={cn(
                  "cursor-pointer rounded-full border-2 border-white shadow transition-transform hover:scale-125",
                  selected ? "h-4 w-4 bg-teal-500" : c.radius_status === "inside" ? "h-3 w-3 bg-navy-400" : "h-3 w-3 bg-navy-200"
                )}
              />
            </Marker>
          );
        })}

      {/* Start / end */}
      {start && (
        <Marker longitude={start.longitude} latitude={start.latitude} anchor="center">
          <div
            title={endIsStart ? `Start & end · ${start.name}` : `Start · ${start.name}`}
            className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-navy-900 text-white shadow-lg"
          >
            <Home className="h-4 w-4" />
          </div>
        </Marker>
      )}
      {end && !endIsStart && (
        <Marker longitude={end.longitude} latitude={end.latitude} anchor="center">
          <div
            title={`End · ${end.name}`}
            className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-navy-600 text-white shadow-lg"
          >
            <Flag className="h-4 w-4" />
          </div>
        </Marker>
      )}

      {/* Numbered stops */}
      {stops
        .filter((s) => s.latitude != null && s.longitude != null)
        .map((s) => (
          <Marker
            key={`stop-${s.company_id}`}
            longitude={s.longitude!}
            latitude={s.latitude!}
            anchor="center"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              onSelectCompany(s.company_id);
            }}
          >
            <div
              title={`${s.sequence}. ${s.company_name}`}
              className={cn(
                "flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border-2 border-white text-xs font-bold text-white shadow-lg transition-transform",
                s.outside_hours || s.late_seconds ? "bg-warning" : "bg-teal-600",
                activeCompanyId === s.company_id && "scale-125 ring-2 ring-teal-300"
              )}
            >
              {s.sequence}
            </div>
          </Marker>
        ))}

      {activeStop && activeStop.latitude != null && activeStop.longitude != null && (
        <Popup
          longitude={activeStop.longitude}
          latitude={activeStop.latitude}
          offset={18}
          closeOnClick={false}
          onClose={() => onSelectCompany(null)}
          maxWidth="280px"
        >
          <div className="space-y-1 p-0.5 text-xs text-navy-700">
            <p className="text-sm font-semibold text-navy-900">
              {activeStop.sequence}. {activeStop.company_name}
            </p>
            {activeStop.address && <p className="text-navy-500">{activeStop.address}</p>}
            <p>
              Arrive <span className="font-medium">{formatClock(activeStop.arrival_time)}</span> · Meeting{" "}
              {formatClock(activeStop.meeting_start)}–{formatClock(activeStop.meeting_end)} ({activeStop.duration_minutes} min)
            </p>
            {activeStop.contact_name && <p>Contact: {activeStop.contact_name}</p>}
            {activeStop.phone && <p>{activeStop.phone}</p>}
            <div className="flex gap-2 pt-1.5">
              <a
                href={navigationUrl(activeStop.latitude, activeStop.longitude)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-md bg-navy-900 px-2 py-1 font-medium text-white hover:bg-navy-800"
              >
                <NavigationIcon className="h-3 w-3" /> Navigate
              </a>
              <button
                type="button"
                onClick={() => onOpenDetails(activeStop.company_id)}
                className="rounded-md border border-navy-200 px-2 py-1 font-medium text-navy-700 hover:bg-navy-50"
              >
                Details
              </button>
            </div>
          </div>
        </Popup>
      )}
      {activeCandidate && activeCandidate.latitude != null && activeCandidate.longitude != null && (
        <Popup
          longitude={activeCandidate.longitude}
          latitude={activeCandidate.latitude}
          offset={12}
          closeOnClick={false}
          onClose={() => onSelectCompany(null)}
          maxWidth="260px"
        >
          <div className="space-y-1 p-0.5 text-xs text-navy-700">
            <p className="text-sm font-semibold text-navy-900">{activeCandidate.company_name}</p>
            {activeCandidate.address && <p className="text-navy-500">{activeCandidate.address}</p>}
            {activeCandidate.distance_miles != null && <p>{activeCandidate.distance_miles.toFixed(1)} mi from start</p>}
            <button
              type="button"
              onClick={() => onOpenDetails(activeCandidate.company_id)}
              className="mt-1 rounded-md border border-navy-200 px-2 py-1 font-medium text-navy-700 hover:bg-navy-50"
            >
              Details
            </button>
          </div>
        </Popup>
      )}
    </Map>
  );
}
