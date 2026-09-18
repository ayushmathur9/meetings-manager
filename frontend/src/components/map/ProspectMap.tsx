"use client";

import "mapbox-gl/dist/mapbox-gl.css";
import Map, { Layer, Marker, NavigationControl, Source, type MapRef } from "react-map-gl/mapbox";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import { CompanyMarker } from "./CompanyMarker";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN || "";
const HAS_REAL_TOKEN = MAPBOX_TOKEN && MAPBOX_TOKEN !== "REPLACE_WITH_REAL_TOKEN";

export interface MapMarkerPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
  status: "unassigned" | "assigned" | "scheduled" | "completed" | "needs_verification";
}

interface LatLng {
  lat: number;
  lng: number;
}

interface Cluster {
  id: string;
  lat: number;
  lng: number;
  points: MapMarkerPoint[];
}

const CLUSTER_PIXEL_RADIUS = 40;
const CLUSTER_MIN_COUNT = 30;

export function ProspectMap({
  markers,
  onMarkerClick,
  center,
  selectedId,
  routeLine,
  cluster = false,
}: {
  markers: MapMarkerPoint[];
  onMarkerClick?: (id: string) => void;
  center?: { lat: number; lng: number };
  selectedId?: string;
  routeLine?: LatLng[];
  cluster?: boolean;
}) {
  const mapRef = useRef<MapRef>(null);
  const [viewTick, setViewTick] = useState(0);

  const markersWithCoords = useMemo(() => markers.filter((m) => m.lat && m.lng), [markers]);

  const mapCenter = useMemo(() => {
    if (center) return center;
    if (markersWithCoords.length === 0) return { lat: 39.8283, lng: -98.5795 };
    return {
      lat: markersWithCoords.reduce((sum, m) => sum + m.lat, 0) / markersWithCoords.length,
      lng: markersWithCoords.reduce((sum, m) => sum + m.lng, 0) / markersWithCoords.length,
    };
  }, [markersWithCoords, center]);

  const shouldCluster = cluster && markersWithCoords.length > CLUSTER_MIN_COUNT;

  const clusters = useMemo<Cluster[] | null>(() => {
    if (!shouldCluster) return null;
    const map = mapRef.current?.getMap();
    if (!map) return markersWithCoords.map((m) => ({ id: m.id, lat: m.lat, lng: m.lng, points: [m] }));

    const buckets: Cluster[] = [];
    for (const m of markersWithCoords) {
      const point = map.project([m.lng, m.lat]);
      let placed = false;
      for (const bucket of buckets) {
        const bucketPoint = map.project([bucket.lng, bucket.lat]);
        const dx = point.x - bucketPoint.x;
        const dy = point.y - bucketPoint.y;
        if (Math.sqrt(dx * dx + dy * dy) < CLUSTER_PIXEL_RADIUS) {
          bucket.points.push(m);
          bucket.lat = bucket.points.reduce((s, p) => s + p.lat, 0) / bucket.points.length;
          bucket.lng = bucket.points.reduce((s, p) => s + p.lng, 0) / bucket.points.length;
          placed = true;
          break;
        }
      }
      if (!placed) {
        buckets.push({ id: m.id, lat: m.lat, lng: m.lng, points: [m] });
      }
    }
    return buckets;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldCluster, markersWithCoords, viewTick]);

  const handleMoveEnd = useCallback(() => {
    if (shouldCluster) setViewTick((t) => t + 1);
  }, [shouldCluster]);

  const hadDataRef = useRef(markersWithCoords.length > 0);
  useEffect(() => {
    const hasData = markersWithCoords.length > 0;
    if (hasData && !hadDataRef.current) {
      const map = mapRef.current?.getMap();
      map?.flyTo({ center: [mapCenter.lng, mapCenter.lat], zoom: 11, duration: 600 });
    }
    hadDataRef.current = hasData;
  }, [markersWithCoords.length, mapCenter]);

  const routeGeoJson = useMemo(() => {
    if (!routeLine || routeLine.length < 2) return null;
    return {
      type: "Feature" as const,
      geometry: {
        type: "LineString" as const,
        coordinates: routeLine.map((p) => [p.lng, p.lat]),
      },
      properties: {},
    };
  }, [routeLine]);

  if (!HAS_REAL_TOKEN) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-navy-200 bg-navy-50 p-8 text-center">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-navy-400 shadow-sm">
          <MapPin className="h-5 w-5" />
        </div>
        <p className="text-sm font-medium text-navy-700">Map preview unavailable</p>
        <p className="max-w-xs text-xs text-navy-500">
          Add a real Mapbox access token to NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN to enable the live
          map. Company data, filtering, and routing still work without it.
        </p>
      </div>
    );
  }

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={MAPBOX_TOKEN}
      initialViewState={{
        longitude: mapCenter.lng,
        latitude: mapCenter.lat,
        zoom: markersWithCoords.length ? 11 : 3.5,
      }}
      onZoomEnd={handleMoveEnd}
      onDragEnd={handleMoveEnd}
      style={{ width: "100%", height: "100%", borderRadius: "0.75rem" }}
      mapStyle="mapbox://styles/mapbox/light-v11"
    >
      <NavigationControl position="top-right" showCompass={false} />

      {routeGeoJson && (
        <Source id="route-line" type="geojson" data={routeGeoJson}>
          <Layer
            id="route-line-layer"
            type="line"
            layout={{ "line-join": "round", "line-cap": "round" }}
            paint={{ "line-color": "#26a69c", "line-width": 3, "line-dasharray": [0.5, 1.5] }}
          />
        </Source>
      )}

      {clusters
        ? clusters.map((c) =>
            c.points.length > 1 ? (
              <Marker key={c.id} longitude={c.lng} latitude={c.lat}>
                <CompanyMarker status="unassigned" count={c.points.length} />
              </Marker>
            ) : (
              <Marker
                key={c.id}
                longitude={c.points[0].lng}
                latitude={c.points[0].lat}
                onClick={(e) => {
                  e.originalEvent.stopPropagation();
                  onMarkerClick?.(c.points[0].id);
                }}
              >
                <div title={c.points[0].label}>
                  <CompanyMarker status={c.points[0].status} selected={c.points[0].id === selectedId} />
                </div>
              </Marker>
            )
          )
        : markersWithCoords.map((m) => (
            <Marker
              key={m.id}
              longitude={m.lng}
              latitude={m.lat}
              onClick={(e) => {
                e.originalEvent.stopPropagation();
                onMarkerClick?.(m.id);
              }}
            >
              <div title={m.label}>
                <CompanyMarker status={m.status} selected={m.id === selectedId} />
              </div>
            </Marker>
          ))}
    </Map>
  );
}
