"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronUp, LocateFixed, MapPinned, Save, Sparkles, SquareCheck } from "lucide-react";
import { usersApi } from "@/lib/api/users";
import { meetingsApi } from "@/lib/api/meetings";
import { companiesApi } from "@/lib/api/companies";
import { prospectsApi } from "@/lib/api/prospects";
import { routesApi } from "@/lib/api/routes";
import { settingsApi } from "@/lib/api/settings";
import type {
  LocationCandidate,
  MeetingDetail,
  NamedLocation,
  PlanDaySummary,
  ProspectListItem,
  RouteOut,
  RouteStopOut,
  User,
} from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProspectMap, MapMarkerPoint } from "@/components/map/ProspectMap";
import { RouteTimeline } from "@/components/routes/RouteTimeline";
import { RouteSummary } from "@/components/routes/RouteSummary";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import { LocationSearchInput } from "@/components/locations/LocationSearchInput";
import { useToast } from "@/components/ui/Toast";

const FALLBACK_START: NamedLocation = {
  name: "Sam IT Solutions Office",
  latitude: 30.2672,
  longitude: -97.7431,
};

const OTHER_OPTION = "__other__";
const RADIUS_OPTIONS = [10, 25, 50];
const TARGET_OPTIONS = [4, 5, 6, 7, 8];

type PlanMode = "auto" | "manual";

interface ManualCandidate {
  companyId: string;
  companyName: string;
  address: string | null;
  distanceMiles: number | null;
  verificationStatus: string | null;
  meetingId: string | null;
  lat: number | null;
  lng: number | null;
}

export default function RoutePlannerPage() {
  const toast = useToast();
  const [mode, setMode] = useState<PlanMode>("auto");
  const [users, setUsers] = useState<User[]>([]);
  const [salespersonId, setSalespersonId] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));

  const [savedLocations, setSavedLocations] = useState<NamedLocation[]>([]);
  const [selectedLocationKey, setSelectedLocationKey] = useState<string>(OTHER_OPTION);
  const [startName, setStartName] = useState(FALLBACK_START.name);
  const [startLat, setStartLat] = useState(String(FALLBACK_START.latitude));
  const [startLng, setStartLng] = useState(String(FALLBACK_START.longitude));
  const [locatingMe, setLocatingMe] = useState(false);
  const [savingLocation, setSavingLocation] = useState(false);

  const [workingStart, setWorkingStart] = useState("09:00");
  const [workingEnd, setWorkingEnd] = useState("17:00");
  const [duration, setDuration] = useState(25);
  const [buffer, setBuffer] = useState(10);
  const [radiusMiles, setRadiusMiles] = useState(25);
  const [targetMeetings, setTargetMeetings] = useState(6);
  const [industry, setIndustry] = useState("");

  const [route, setRoute] = useState<RouteOut | null>(null);
  const [summary, setSummary] = useState<PlanDaySummary | null>(null);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formCollapsed, setFormCollapsed] = useState(false);

  const [manualCandidates, setManualCandidates] = useState<ManualCandidate[]>([]);
  const [manualLoading, setManualLoading] = useState(false);
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<Set<string>>(new Set());
  const [todaysMeetings, setTodaysMeetings] = useState<MeetingDetail[]>([]);
  const [selectedStopId, setSelectedStopId] = useState<string | undefined>(undefined);

  useEffect(() => {
    usersApi.list().then((u) => {
      const sales = u.filter((x) => x.role === "salesperson");
      setUsers(sales);
      if (sales[0]) setSalespersonId(sales[0].id);
    });
  }, []);

  useEffect(() => {
    settingsApi.get().then((s) => {
      const locations = s.saved_locations ?? [];
      setSavedLocations(locations);
      const initial = s.default_start_location ?? locations[0] ?? null;
      if (initial) {
        setSelectedLocationKey(initial.name);
        setStartName(initial.name);
        setStartLat(String(initial.latitude));
        setStartLng(String(initial.longitude));
      }
      if (s.working_hours_start) setWorkingStart(s.working_hours_start.slice(0, 5));
      if (s.working_hours_end) setWorkingEnd(s.working_hours_end.slice(0, 5));
      if (s.default_meeting_duration_minutes) setDuration(s.default_meeting_duration_minutes);
      if (s.default_travel_buffer_minutes) setBuffer(s.default_travel_buffer_minutes);
    });
  }, []);

  useEffect(() => {
    if (!salespersonId || !date) return;
    routesApi.getByDate(salespersonId, date).then((r) => {
      setRoute(r);
      setSummary(null);
      setFormCollapsed(!!r && r.stops.length > 0);
    });
  }, [salespersonId, date]);

  useEffect(() => {
    if (mode !== "manual" || !salespersonId) return;
    let cancelled = false;
    setManualLoading(true);
    Promise.all([
      prospectsApi.list({
        assigned_user_id: salespersonId,
        industry: industry.trim() || undefined,
        center_lat: startLat ? Number(startLat) : undefined,
        center_lng: startLng ? Number(startLng) : undefined,
        radius_miles: radiusMiles,
        page_size: 500,
      }),
      meetingsApi.list({ salesperson_id: salespersonId, date_from: date, date_to: date }),
    ]).then(([page, meetings]) => {
      if (cancelled) return;
      const activeMeetings = meetings.filter((m) => m.status !== "cancelled");
      setTodaysMeetings(activeMeetings);
      const meetingByCompany = new Map(activeMeetings.map((m) => [m.company_id, m]));
      const candidates: ManualCandidate[] = page.items.map((p: ProspectListItem) => ({
        companyId: p.company_id,
        companyName: p.company_name,
        address: [p.address_line_1, p.city, p.state].filter(Boolean).join(", ") || null,
        distanceMiles: p.distance_meters != null ? p.distance_meters / 1609.34 : null,
        verificationStatus: p.verification_status,
        meetingId: meetingByCompany.get(p.company_id)?.id ?? null,
        lat: p.latitude,
        lng: p.longitude,
      }));
      setManualCandidates(candidates);
      setSelectedCompanyIds((prev) => {
        const next = new Set(prev);
        for (const c of candidates) {
          if (c.meetingId) next.add(c.companyId);
        }
        return next;
      });
      setManualLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [mode, salespersonId, date, industry, radiusMiles, startLat, startLng]);

  function handleSelectSavedLocation(key: string) {
    setSelectedLocationKey(key);
    if (key === OTHER_OPTION) return;
    const loc = savedLocations.find((l) => l.name === key);
    if (loc) {
      setStartName(loc.name);
      setStartLat(String(loc.latitude));
      setStartLng(String(loc.longitude));
    }
  }

  function handleSearchSelect(candidate: LocationCandidate) {
    setSelectedLocationKey(OTHER_OPTION);
    setStartName(candidate.name || candidate.formatted_address);
    setStartLat(String(candidate.latitude));
    setStartLng(String(candidate.longitude));
  }

  function handleUseMyLocation() {
    if (!navigator.geolocation) {
      toast({ title: "Location not supported", description: "Your browser doesn't support geolocation.", variant: "error" });
      return;
    }
    setLocatingMe(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setSelectedLocationKey(OTHER_OPTION);
        setStartName("My current location");
        setStartLat(String(position.coords.latitude));
        setStartLng(String(position.coords.longitude));
        setLocatingMe(false);
        toast({ title: "Using your current location", variant: "success" });
      },
      (err) => {
        setLocatingMe(false);
        toast({
          title: "Couldn't get your location",
          description: err.message || "Check your browser's location permission.",
          variant: "error",
        });
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function handleSaveLocation() {
    if (!startName.trim() || !startLat || !startLng) return;
    setSavingLocation(true);
    try {
      const newLocation: NamedLocation = {
        name: startName.trim(),
        latitude: Number(startLat),
        longitude: Number(startLng),
      };
      const next = [...savedLocations.filter((l) => l.name !== newLocation.name), newLocation];
      await settingsApi.update({ saved_locations: next });
      setSavedLocations(next);
      setSelectedLocationKey(newLocation.name);
      toast({ title: "Location saved", description: newLocation.name, variant: "success" });
    } catch (err) {
      toast({ title: "Couldn't save location", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setSavingLocation(false);
    }
  }

  async function handlePlanDay() {
    if (!salespersonId) return;
    setPlanning(true);
    setError(null);
    try {
      const result = await routesApi.plan({
        salesperson_id: salespersonId,
        date,
        start_location: { name: startName, latitude: Number(startLat), longitude: Number(startLng) },
        working_hours_start: `${workingStart}:00`,
        working_hours_end: `${workingEnd}:00`,
        meeting_duration_minutes: duration,
        travel_buffer_minutes: buffer,
        target_meetings: targetMeetings,
        radius_miles: radiusMiles,
        industry: industry.trim() || null,
      });
      setRoute(result.route);
      setSummary(result.summary);
      setFormCollapsed(true);
      toast({
        title: "Day planned",
        description: `${result.route.stops.length} stops scheduled from ${result.summary.eligible_count} eligible prospects`,
        variant: "success",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to plan the day");
    } finally {
      setPlanning(false);
    }
  }

  function toggleCompanySelection(companyId: string) {
    setSelectedCompanyIds((prev) => {
      const next = new Set(prev);
      if (next.has(companyId)) next.delete(companyId);
      else next.add(companyId);
      return next;
    });
  }

  async function handleBuildFromSelection() {
    if (!salespersonId || selectedCompanyIds.size === 0) return;
    setPlanning(true);
    setError(null);
    try {
      const selected = manualCandidates.filter((c) => selectedCompanyIds.has(c.companyId));
      const needsMeeting = selected.filter((c) => !c.meetingId);
      const alreadyScheduled = selected.filter((c) => c.meetingId);

      const newMeetingIds: string[] = [];
      for (let i = 0; i < needsMeeting.length; i++) {
        const candidate = needsMeeting[i];
        const company = await companiesApi.get(candidate.companyId);
        const startMinutes =
          Number(workingStart.split(":")[0]) * 60 + Number(workingStart.split(":")[1]) + i * (duration + buffer);
        const h = Math.floor(startMinutes / 60) % 24;
        const m = startMinutes % 60;
        const placeholderStart = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        const meeting = await meetingsApi.create({
          company_id: candidate.companyId,
          contact_id: company.contacts[0]?.id ?? null,
          salesperson_id: salespersonId,
          date,
          start_time: `${placeholderStart}:00`,
          duration_minutes: duration,
        });
        newMeetingIds.push(meeting.id);
      }

      const meetingIds = [...alreadyScheduled.map((c) => c.meetingId!), ...newMeetingIds];
      const result = await routesApi.generate({
        salesperson_id: salespersonId,
        date,
        start_location: { name: startName, latitude: Number(startLat), longitude: Number(startLng) },
        working_hours_start: `${workingStart}:00`,
        working_hours_end: `${workingEnd}:00`,
        meeting_duration_minutes: duration,
        travel_buffer_minutes: buffer,
        meeting_ids: meetingIds,
      });
      setRoute(result);
      setSummary(null);
      setFormCollapsed(true);
      toast({
        title: "Route built",
        description: `${result.stops.length} of ${selected.length} selected stops scheduled`,
        variant: "success",
      });
      meetingsApi.list({ salesperson_id: salespersonId, date_from: date, date_to: date }).then((data) => {
        setTodaysMeetings(data.filter((m) => m.status !== "cancelled"));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build the route");
    } finally {
      setPlanning(false);
    }
  }

  async function handleRemoveStop(stop: RouteStopOut) {
    if (!route) return;
    try {
      await meetingsApi.update(stop.meeting_id, { status: "cancelled" });
      const remainingMeetingIds = route.stops.filter((s) => s.id !== stop.id).map((s) => s.meeting_id);
      if (remainingMeetingIds.length === 0) {
        setRoute({ ...route, stops: [] });
        return;
      }
      const updated = await routesApi.generate({
        salesperson_id: salespersonId,
        date,
        start_location: { name: startName, latitude: Number(startLat), longitude: Number(startLng) },
        working_hours_start: `${workingStart}:00`,
        working_hours_end: `${workingEnd}:00`,
        meeting_duration_minutes: duration,
        travel_buffer_minutes: buffer,
        meeting_ids: remainingMeetingIds,
      });
      setRoute(updated);
      toast({ title: "Stop removed", description: "Route recalculated", variant: "success" });
    } catch (err) {
      toast({ title: "Couldn't remove stop", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  const markers: MapMarkerPoint[] = [
    { id: "start", lat: Number(startLat), lng: Number(startLng), label: startName, status: "assigned" },
    ...(route?.stops || [])
      .filter((s) => s.latitude && s.longitude)
      .map((s) => ({
        id: s.meeting_id,
        lat: s.latitude!,
        lng: s.longitude!,
        label: `${s.sequence}. ${s.company_name}`,
        status: "scheduled" as const,
      })),
  ];

  const routeLine = useMemo(() => {
    if (!route) return undefined;
    const points = [{ lat: Number(startLat), lng: Number(startLng) }];
    route.stops
      .filter((s) => s.latitude && s.longitude)
      .forEach((s) => points.push({ lat: s.latitude!, lng: s.longitude! }));
    return points.length > 1 ? points : undefined;
  }, [route, startLat, startLng]);

  const availableLabel = useMemo(() => {
    if (!summary || summary.available_seconds <= 0) return null;
    const minutes = Math.round(summary.available_seconds / 60);
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
  }, [summary]);

  return (
    <div className="flex h-full flex-col p-6 pb-0">
      <PageHeader title="Routes" description="Plan and manage the sales day." />

      <Card className="mb-4">
        <CardBody>
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-navy-800">
              <Sparkles className="h-4 w-4 text-teal-600" />
              Plan your sales day
            </h2>
            {route && (
              <button
                type="button"
                onClick={() => setFormCollapsed((c) => !c)}
                className="flex items-center gap-1 text-xs font-medium text-navy-500 hover:text-navy-800"
              >
                {formCollapsed ? "Route settings" : "Collapse"}
                {formCollapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
              </button>
            )}
          </div>
          {!formCollapsed && (
            <>
              <div className="mb-3 mt-1 inline-flex rounded-lg border border-navy-200 p-0.5 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setMode("auto")}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors ${
                    mode === "auto" ? "bg-navy-900 text-white" : "text-navy-600 hover:bg-navy-50"
                  }`}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Auto-select
                </button>
                <button
                  type="button"
                  onClick={() => setMode("manual")}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors ${
                    mode === "manual" ? "bg-navy-900 text-white" : "text-navy-600 hover:bg-navy-50"
                  }`}
                >
                  <SquareCheck className="h-3.5 w-3.5" />
                  Choose manually
                </button>
              </div>
              <p className="mb-3 text-xs text-navy-500">
                {mode === "auto"
                  ? "The system picks a geographically sensible set of prospects for you."
                  : "Check the prospects you want to visit, then build the route from your selection."}
              </p>
              <div className="flex flex-wrap items-end gap-3 text-sm">
                <Field label="Salesperson">
                  <select
                    value={salespersonId}
                    onChange={(e) => setSalespersonId(e.target.value)}
                    className="rounded-lg border border-navy-200 px-2 py-1.5"
                  >
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Date">
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="rounded-lg border border-navy-200 px-2 py-1.5"
                  />
                </Field>
                <Field label="Start location">
                  <div className="flex items-center gap-1.5">
                    <select
                      value={selectedLocationKey}
                      onChange={(e) => handleSelectSavedLocation(e.target.value)}
                      className="w-48 rounded-lg border border-navy-200 px-2 py-1.5"
                    >
                      {savedLocations.map((l) => (
                        <option key={l.name} value={l.name}>
                          {l.name}
                        </option>
                      ))}
                      <option value={OTHER_OPTION}>Other...</option>
                    </select>
                    <button
                      type="button"
                      onClick={handleUseMyLocation}
                      disabled={locatingMe}
                      title="Use my current location"
                      className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg border border-navy-200 text-navy-500 transition-colors hover:bg-navy-50 disabled:opacity-50"
                    >
                      <LocateFixed className={locatingMe ? "h-4 w-4 animate-pulse" : "h-4 w-4"} />
                    </button>
                  </div>
                </Field>
                {selectedLocationKey === OTHER_OPTION && (
                  <Field label="Search for a location">
                    <div className="flex items-start gap-1">
                      <div className="w-64">
                        <LocationSearchInput onSelect={handleSearchSelect} />
                        {startLat && startLng && (
                          <p className="mt-1 truncate text-xs text-navy-500" title={startName}>
                            {startName} ({Number(startLat).toFixed(4)}, {Number(startLng).toFixed(4)})
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={handleSaveLocation}
                        disabled={savingLocation || !startLat || !startLng}
                        title="Save as a reusable location"
                        className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg border border-navy-200 text-navy-500 transition-colors hover:bg-navy-50 disabled:opacity-50"
                      >
                        <Save className="h-4 w-4" />
                      </button>
                    </div>
                  </Field>
                )}
                <Field label="Working hours">
                  <div className="flex gap-1">
                    <input
                      type="time"
                      value={workingStart}
                      onChange={(e) => setWorkingStart(e.target.value)}
                      className="rounded-lg border border-navy-200 px-2 py-1.5"
                    />
                    <input
                      type="time"
                      value={workingEnd}
                      onChange={(e) => setWorkingEnd(e.target.value)}
                      className="rounded-lg border border-navy-200 px-2 py-1.5"
                    />
                  </div>
                </Field>
                <Field label="Duration / buffer (min)">
                  <div className="flex gap-1">
                    <input
                      type="number"
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                      className="w-16 rounded-lg border border-navy-200 px-2 py-1.5"
                    />
                    <input
                      type="number"
                      value={buffer}
                      onChange={(e) => setBuffer(Number(e.target.value))}
                      className="w-16 rounded-lg border border-navy-200 px-2 py-1.5"
                    />
                  </div>
                </Field>
                <Field label="Territory radius">
                  <select
                    value={radiusMiles}
                    onChange={(e) => setRadiusMiles(Number(e.target.value))}
                    className="rounded-lg border border-navy-200 px-2 py-1.5"
                  >
                    {RADIUS_OPTIONS.map((r) => (
                      <option key={r} value={r}>
                        {r} mi
                      </option>
                    ))}
                  </select>
                </Field>
                {mode === "auto" && (
                  <Field label="Target meetings">
                    <select
                      value={targetMeetings}
                      onChange={(e) => setTargetMeetings(Number(e.target.value))}
                      className="rounded-lg border border-navy-200 px-2 py-1.5"
                    >
                      {TARGET_OPTIONS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <Field label="Industry (optional)">
                  <input
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                    placeholder="e.g. healthcare"
                    className="w-36 rounded-lg border border-navy-200 px-2 py-1.5"
                  />
                </Field>
                {mode === "auto" ? (
                  <Button onClick={handlePlanDay} disabled={planning || !salespersonId}>
                    {planning ? "Planning..." : "Plan My Day"}
                  </Button>
                ) : (
                  <Button onClick={handleBuildFromSelection} disabled={planning || selectedCompanyIds.size === 0}>
                    {planning ? "Building..." : `Build Route (${selectedCompanyIds.size})`}
                  </Button>
                )}
              </div>
              {error && <p className="mt-2 text-sm text-danger">{error}</p>}

              {mode === "manual" && (
                <div className="mt-4">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">
                    {manualLoading
                      ? "Loading prospects..."
                      : `${manualCandidates.length} prospect${manualCandidates.length === 1 ? "" : "s"} in territory · ${selectedCompanyIds.size} selected`}
                  </h3>
                  {!manualLoading && manualCandidates.length === 0 ? (
                    <EmptyState
                      icon={<MapPinned className="h-5 w-5" />}
                      title="No prospects found"
                      description="This salesperson has no assigned prospects in this territory. Assign prospects or widen the radius."
                    />
                  ) : (
                    <div className="max-h-72 overflow-y-auto rounded-lg border border-navy-100">
                      {manualCandidates.map((c) => {
                        const hasLocation = c.lat != null && c.lng != null;
                        return (
                          <label
                            key={c.companyId}
                            className={`flex items-center gap-2 border-b border-navy-50 px-3 py-2 text-sm last:border-b-0 ${
                              hasLocation ? "cursor-pointer hover:bg-navy-50" : "cursor-not-allowed opacity-50"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={selectedCompanyIds.has(c.companyId)}
                              disabled={!hasLocation}
                              onChange={() => toggleCompanySelection(c.companyId)}
                            />
                            <span className="flex-1 min-w-0">
                              <span className="block truncate font-medium text-navy-800">{c.companyName}</span>
                              <span className="block truncate text-xs text-navy-500">
                                {c.address || "No address on file"}
                                {c.distanceMiles != null && ` · ${c.distanceMiles.toFixed(1)} mi`}
                              </span>
                            </span>
                            {!hasLocation ? (
                              <Badge tone="warning">needs location</Badge>
                            ) : c.meetingId ? (
                              <Badge tone="success">scheduled</Badge>
                            ) : null}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
          {formCollapsed && summary && (
            <p className="mt-1 text-xs text-navy-500">
              {summary.eligible_count} eligible prospects · {summary.verified_count} with verified locations ·{" "}
              {summary.in_territory_count} in territory · {summary.scheduled_count} scheduled today
              {summary.excluded_unverified_count > 0 &&
                ` · ${summary.excluded_unverified_count} excluded (unverified location)`}
            </p>
          )}
        </CardBody>
      </Card>

      {summary && !summary.fits_within_working_hours && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          This day runs past working hours ({workingEnd}). Reduce the target meeting count or extend working hours.
        </div>
      )}

      {route && route.stops.length > 0 ? (
        <div className="flex flex-1 gap-4 overflow-hidden pb-6">
          <div className="scrollbar-thin w-[38%] space-y-4 overflow-y-auto pr-1">
            <RouteSummary route={route} />
            {availableLabel && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-navy-100 bg-navy-50/60 px-4 py-3 text-sm">
                <div>
                  <p className="font-medium text-navy-800">Available time</p>
                  <p className="text-xs text-navy-500">{availableLabel} unused before {workingEnd}</p>
                </div>
              </div>
            )}
            <RouteTimeline
              route={route}
              onRemoveStop={handleRemoveStop}
              selectedStopId={selectedStopId}
              onSelectStop={setSelectedStopId}
            />
          </div>
          <div className="w-[62%] pb-2">
            <ProspectMap
              markers={markers}
              routeLine={routeLine}
              selectedId={selectedStopId}
              onMarkerClick={setSelectedStopId}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center pb-6">
          <EmptyState
            icon={<MapPinned className="h-5 w-5" />}
            title="No route planned yet"
            description="Choose a salesperson, territory, and target meeting count, then click Plan My Day."
          />
        </div>
      )}
      <p className="pb-4 text-center text-xs text-navy-400">
        <Link href="/admin/prospects" className="font-medium text-teal-600 hover:text-teal-700">
          Review prospects and locations
        </Link>
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-navy-600">{label}</label>
      {children}
    </div>
  );
}
