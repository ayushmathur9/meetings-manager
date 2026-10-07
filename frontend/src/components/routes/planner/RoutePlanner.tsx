"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  Car,
  Clock,
  Loader2,
  LocateFixed,
  MapPinned,
  Plus,
  RefreshCw,
  Route as RouteIcon,
  Save,
  Sparkles,
  Timer,
  Trash2,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError, type ApiErrorCompany } from "@/lib/api/client";
import { routePlannerApi } from "@/lib/api/routes";
import { prospectsApi } from "@/lib/api/prospects";
import { settingsApi } from "@/lib/api/settings";
import { usersApi } from "@/lib/api/users";
import type {
  CandidatesOut,
  LocationCandidate,
  NamedLocation,
  ProspectPriority,
  RouteListItem,
  RoutePlan,
  RouteStatus,
  User,
} from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { LocationSearchInput } from "@/components/locations/LocationSearchInput";
import { ProspectDrawer } from "@/components/prospects/ProspectDrawer";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";
import { formatClock, formatDate, formatDuration, formatMiles, todayIso } from "./format";
import { PlanTimeline } from "./PlanTimeline";
import { ProspectPicker } from "./ProspectPicker";
import { RoutePlannerMap } from "./RoutePlannerMap";

const DURATION_OPTIONS = [15, 20, 25, 30, 45, 60];
const RADIUS_OPTIONS = [5, 10, 15, 20, 25, 30, 50];
const CUSTOM = "__custom__";
const ENGINE_LABELS: Record<string, string> = { geoapify: "Geoapify", mapbox: "Mapbox", google_maps: "Google Maps" };

interface PlanErrorState {
  message: string;
  code?: string;
  companies: ApiErrorCompany[];
}

const toApiTime = (hhmm: string) => (hhmm.length === 5 ? `${hhmm}:00` : hhmm);
const fromApiTime = (value: string) => value.slice(0, 5);

export function RoutePlanner() {
  const { user } = useAuth();
  const toast = useToast();
  const isAdmin = user?.role === "admin";

  // ----------------------------------------------------------------- config
  const [salespeople, setSalespeople] = useState<User[]>([]);
  const [salespersonId, setSalespersonId] = useState<string>("");
  const [savedLocations, setSavedLocations] = useState<NamedLocation[]>([]);
  const [startKey, setStartKey] = useState<string>(CUSTOM);
  const [start, setStart] = useState<NamedLocation | null>(null);
  const [date, setDate] = useState(todayIso());
  const [workStart, setWorkStart] = useState("08:30");
  const [workEnd, setWorkEnd] = useState("16:30");
  const [duration, setDuration] = useState(25);
  const [buffer, setBuffer] = useState(0);
  const [radius, setRadius] = useState(20);
  const [allowOvertime, setAllowOvertime] = useState(false);
  const [routeName, setRouteName] = useState("");
  const [scope, setScope] = useState<"assigned" | "all">("assigned");
  const [locatingMe, setLocatingMe] = useState(false);

  // ----------------------------------------------------------------- data
  const [candidates, setCandidates] = useState<CandidatesOut | null>(null);
  const [candLoading, setCandLoading] = useState(false);
  const [candError, setCandError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [durations, setDurations] = useState<Record<string, number>>({});
  const [plan, setPlan] = useState<RoutePlan | null>(null);
  const [dirty, setDirty] = useState(false);
  const [planning, setPlanning] = useState<"optimize" | "recalculate" | null>(null);
  const [planError, setPlanError] = useState<PlanErrorState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedRouteId, setSavedRouteId] = useState<string | null>(null);
  const [savedStatus, setSavedStatus] = useState<RouteStatus | null>(null);
  const [stale, setStale] = useState(false);
  const [savedRoutes, setSavedRoutes] = useState<RouteListItem[]>([]);
  const [locatingIds, setLocatingIds] = useState<Set<string>>(new Set());
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);
  const [drawerCompanyId, setDrawerCompanyId] = useState<string | null>(null);
  const [confirmReplace, setConfirmReplace] = useState<RouteListItem | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<RouteListItem | null>(null);

  const effectiveSalespersonId = isAdmin ? salespersonId : user?.id ?? "";
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const candidatesById = useMemo(
    () => new Map((candidates?.candidates ?? []).map((c) => [c.company_id, c])),
    [candidates]
  );
  // The day ends at the last meeting. Older saved routes may still carry an
  // end location; it's shown as saved, and dropped on recalculation.
  const savedEnd =
    plan && !dirty
      ? plan.config.end_mode === "same_as_start"
        ? plan.config.start_location
        : plan.config.end_mode === "custom"
          ? plan.config.end_location ?? null
          : null
      : null;

  /** Any edit after a plan exists means the shown times are out of date. */
  const touch = useCallback(() => {
    if (plan) setDirty(true);
  }, [plan]);

  // ----------------------------------------------------------------- bootstrap
  useEffect(() => {
    usersApi.list().then((u) => {
      const sales = u.filter((x) => x.role === "salesperson");
      setSalespeople(sales);
      if (sales[0]) setSalespersonId((prev) => prev || sales[0].id);
    });
    settingsApi.get().then((s) => {
      const locations = s.saved_locations ?? [];
      setSavedLocations(locations);
      const initial = s.default_start_location ?? locations[0] ?? null;
      if (initial) {
        setStart(initial);
        setStartKey(initial.name);
      }
      if (s.default_meeting_duration_minutes) setDuration(s.default_meeting_duration_minutes);
    });
  }, []);

  // ----------------------------------------------------------------- candidates (PostGIS)
  const loadCandidates = useCallback(async () => {
    if (!start || !effectiveSalespersonId) return;
    setCandLoading(true);
    setCandError(null);
    try {
      const data = await routePlannerApi.preview({
        salesperson_id: effectiveSalespersonId,
        date,
        start_location: start,
        radius_miles: radius,
        scope,
      });
      setCandidates(data);
      // The radius is a hard filter: drop selections that are now outside it.
      const inside = new Set(data.candidates.filter((c) => c.radius_status === "inside").map((c) => c.company_id));
      setSelectedIds((prev) => {
        const next = prev.filter((id) => inside.has(id));
        return next.length === prev.length ? prev : next;
      });
    } catch (err) {
      setCandError(err instanceof Error ? err.message : "Couldn't load prospects");
    } finally {
      setCandLoading(false);
    }
  }, [start, effectiveSalespersonId, date, radius, scope]);

  useEffect(() => {
    const t = setTimeout(loadCandidates, 200);
    return () => clearTimeout(t);
  }, [loadCandidates]);

  const loadSavedRoutes = useCallback(async () => {
    if (!effectiveSalespersonId) return;
    const list = await routePlannerApi.list(isAdmin ? { salesperson_id: effectiveSalespersonId } : {});
    setSavedRoutes(list);
  }, [effectiveSalespersonId, isAdmin]);

  useEffect(() => {
    loadSavedRoutes().catch(() => setSavedRoutes([]));
  }, [loadSavedRoutes]);

  // ----------------------------------------------------------------- handlers
  function chooseStart(key: string) {
    setStartKey(key);
    const loc = savedLocations.find((l) => l.name === key);
    if (loc) {
      setStart(loc);
      touch();
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      toast({ title: "Location not supported", variant: "error" });
      return;
    }
    setLocatingMe(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setStartKey(CUSTOM);
        setStart({ name: "My current location", latitude: pos.coords.latitude, longitude: pos.coords.longitude });
        setLocatingMe(false);
        touch();
      },
      (err) => {
        setLocatingMe(false);
        toast({ title: "Couldn't get your location", description: err.message, variant: "error" });
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  async function saveStartAsLocation() {
    if (!start) return;
    const next = [...savedLocations.filter((l) => l.name !== start.name), start];
    try {
      await settingsApi.update({ saved_locations: next });
      setSavedLocations(next);
      setStartKey(start.name);
      toast({ title: "Location saved", description: start.name, variant: "success" });
    } catch (err) {
      toast({ title: "Couldn't save location", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  function candidateToLocation(c: LocationCandidate): NamedLocation {
    return { name: c.name || c.formatted_address, address: c.formatted_address, latitude: c.latitude, longitude: c.longitude };
  }

  function toggle(companyId: string) {
    setSelectedIds((prev) => (prev.includes(companyId) ? prev.filter((x) => x !== companyId) : [...prev, companyId]));
    touch();
  }

  function selectMany(ids: string[], selected: boolean) {
    setSelectedIds((prev) =>
      selected ? [...prev, ...ids.filter((id) => !prev.includes(id))] : prev.filter((id) => !ids.includes(id))
    );
    touch();
  }

  async function changePriority(companyId: string, priority: ProspectPriority) {
    setCandidates((prev) =>
      prev && {
        ...prev,
        candidates: prev.candidates.map((c) => (c.company_id === companyId ? { ...c, priority } : c)),
      }
    );
    try {
      await prospectsApi.setPriority(companyId, priority);
      touch();
    } catch (err) {
      toast({ title: "Couldn't update priority", description: err instanceof Error ? err.message : undefined, variant: "error" });
      loadCandidates();
    }
  }

  async function locate(companyIds: string[]) {
    setLocatingIds((prev) => new Set([...prev, ...companyIds]));
    try {
      const results = await routePlannerApi.geocodeMissing(companyIds);
      const found = results.filter((r) => r.status === "verified" || r.status === "already_verified");
      const review = results.filter((r) => r.status === "needs_review" || r.status === "failed");
      toast({
        title: found.length ? `Located ${found.length} of ${results.length}` : "No confident match",
        description: review.length
          ? `${review.map((r) => r.company_name).join(", ")} need${review.length === 1 ? "s" : ""} manual review on the prospect page.`
          : undefined,
        variant: found.length ? "success" : "error",
        duration: 6000,
      });
      await loadCandidates();
      setPlanError(null);
    } catch (err) {
      toast({ title: "Couldn't locate prospects", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setLocatingIds((prev) => new Set([...prev].filter((id) => !companyIds.includes(id))));
    }
  }

  function buildConfig() {
    return {
      salesperson_id: effectiveSalespersonId || null,
      date,
      name: routeName.trim() || null,
      start_location: start!,
      end_mode: "none" as const,
      end_location: null,
      working_hours_start: toApiTime(workStart),
      working_hours_end: toApiTime(workEnd),
      meeting_duration_minutes: duration,
      travel_buffer_minutes: buffer,
      radius_miles: radius,
      allow_overtime: allowOvertime,
    };
  }

  async function runPlan(optimize: boolean) {
    if (!start || selectedIds.length === 0) return;
    setPlanning(optimize ? "optimize" : "recalculate");
    setPlanError(null);
    try {
      const result = await routePlannerApi.optimize({
        ...buildConfig(),
        stops: selectedIds.map((id) => ({ company_id: id, duration_minutes: durations[id] ?? null })),
        optimize,
      });
      setPlan(result);
      setSelectedIds([...result.stops.map((s) => s.company_id), ...result.unscheduled.map((u) => u.company_id)]);
      setDirty(false);
      setStale(false);
      setActiveCompanyId(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setPlanError({ message: err.message, code: err.code, companies: err.companies });
      } else {
        setPlanError({ message: "Something went wrong generating the route.", companies: [] });
      }
    } finally {
      setPlanning(null);
    }
  }

  async function recalculateSaved() {
    if (!savedRouteId) return;
    setPlanning("recalculate");
    setPlanError(null);
    try {
      const result = await routePlannerApi.recalculate(savedRouteId, false);
      setPlan(result);
      setSelectedIds([...result.stops.map((s) => s.company_id), ...result.unscheduled.map((u) => u.company_id)]);
      setDirty(false);
      setStale(false);
      toast({ title: "Recalculated with current locations", description: "Save to keep the updated plan.", variant: "info" });
    } catch (err) {
      setPlanError({
        message: err instanceof Error ? err.message : "Recalculation failed",
        code: err instanceof ApiError ? err.code : undefined,
        companies: err instanceof ApiError ? err.companies : [],
      });
    } finally {
      setPlanning(null);
    }
  }

  async function save(force = false) {
    if (!plan || dirty) return;
    if (!savedRouteId && !force) {
      const existing = savedRoutes.find((r) => r.date === plan.config.date);
      if (existing) {
        setConfirmReplace(existing);
        return;
      }
    }
    setSaving(true);
    try {
      const planToSave = { ...plan, config: { ...plan.config, name: routeName.trim() || null } };
      const saved = savedRouteId
        ? await routePlannerApi.update(savedRouteId, { plan: planToSave })
        : await routePlannerApi.save(planToSave);
      setSavedRouteId(saved.id);
      setSavedStatus(saved.status);
      setPlan(saved);
      setStale(saved.is_stale);
      await loadSavedRoutes();
      toast({
        title: "Route saved",
        description: `${saved.stops.length} meetings on ${formatDate(saved.config.date)} added to the calendar.`,
        variant: "success",
      });
    } catch (err) {
      toast({ title: "Couldn't save route", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function openSaved(routeId: string) {
    try {
      const route = await routePlannerApi.get(routeId);
      const c = route.config;
      setDate(c.date);
      setStart(c.start_location);
      setStartKey(savedLocations.some((l) => l.name === c.start_location.name) ? c.start_location.name : CUSTOM);
      setWorkStart(fromApiTime(c.working_hours_start));
      setWorkEnd(fromApiTime(c.working_hours_end));
      setDuration(c.meeting_duration_minutes);
      setBuffer(c.travel_buffer_minutes);
      setRadius(c.radius_miles);
      setAllowOvertime(c.allow_overtime);
      setRouteName(c.name ?? "");
      setSelectedIds([...route.stops.map((s) => s.company_id), ...route.unscheduled.map((u) => u.company_id)]);
      setDurations(
        Object.fromEntries(
          route.stops.filter((s) => s.duration_minutes !== c.meeting_duration_minutes).map((s) => [s.company_id, s.duration_minutes])
        )
      );
      setPlan(route);
      setSavedRouteId(route.id);
      setSavedStatus(route.status);
      setStale(route.is_stale);
      setDirty(false);
      setPlanError(null);
      setActiveCompanyId(null);
    } catch (err) {
      toast({ title: "Couldn't open route", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  async function deleteSaved(item: RouteListItem) {
    try {
      await routePlannerApi.remove(item.id);
      if (item.id === savedRouteId) newRoute();
      await loadSavedRoutes();
      toast({ title: "Route deleted", variant: "success" });
    } catch (err) {
      toast({ title: "Couldn't delete route", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  function newRoute() {
    setPlan(null);
    setSavedRouteId(null);
    setSavedStatus(null);
    setStale(false);
    setSelectedIds([]);
    setDurations({});
    setDirty(false);
    setPlanError(null);
    setRouteName("");
  }

  // ----------------------------------------------------------------- render
  const canGenerate = !!start && selectedIds.length > 0 && !planning;
  const shownStops = plan && !dirty ? plan.stops : plan?.stops.filter((s) => selectedSet.has(s.company_id)) ?? [];

  return (
    <div className="p-6">
      <PageHeader
        title="Route Planner"
        description="Plan an optimized sales day: pick prospects, generate the route, and save it to the calendar."
        actions={
          plan && (
            <Button variant="secondary" onClick={newRoute}>
              <Plus className="h-4 w-4" /> New route
            </Button>
          )
        }
      />

      <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
        {/* ------------------------------------------------ left: settings + prospects */}
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-navy-900">
                <RouteIcon className="h-4 w-4 text-teal-600" /> Day settings
              </h2>
              {savedRouteId && (
                <span className="rounded-full bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-700">
                  Saved · {savedStatus}
                </span>
              )}
            </CardHeader>
            <CardBody className="space-y-3.5">
              {isAdmin && (
                <Field label="Salesperson">
                  <select
                    value={salespersonId}
                    onChange={(e) => {
                      setSalespersonId(e.target.value);
                      newRoute();
                    }}
                    className={inputClass}
                  >
                    {salespeople.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              <Field label="Start location">
                <div className="flex gap-1.5">
                  <select value={startKey} onChange={(e) => chooseStart(e.target.value)} className={inputClass}>
                    {savedLocations.map((l) => (
                      <option key={l.name} value={l.name}>
                        {l.name}
                      </option>
                    ))}
                    <option value={CUSTOM}>Custom location…</option>
                  </select>
                  <IconBtn title="Use my current location" onClick={useMyLocation} disabled={locatingMe}>
                    <LocateFixed className={cn("h-4 w-4", locatingMe && "animate-pulse")} />
                  </IconBtn>
                </div>
                {startKey === CUSTOM && (
                  <div className="mt-1.5 flex items-start gap-1.5">
                    <div className="flex-1">
                      <LocationSearchInput
                        placeholder="Search an address or place…"
                        onSelect={(c) => {
                          setStart(candidateToLocation(c));
                          touch();
                        }}
                      />
                    </div>
                    {isAdmin && start && (
                      <IconBtn title="Save as a reusable location" onClick={saveStartAsLocation}>
                        <Save className="h-4 w-4" />
                      </IconBtn>
                    )}
                  </div>
                )}
                {start && <p className="mt-1 truncate text-xs text-navy-500">{start.address || start.name}</p>}
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Date">
                  <input
                    type="date"
                    value={date}
                    onChange={(e) => {
                      setDate(e.target.value);
                      touch();
                    }}
                    className={inputClass}
                  />
                </Field>
                <Field label="Radius">
                  <select
                    value={radius}
                    onChange={(e) => {
                      setRadius(Number(e.target.value));
                      touch();
                    }}
                    className={inputClass}
                  >
                    {Array.from(new Set([...RADIUS_OPTIONS, radius])).sort((a, b) => a - b).map((r) => (
                      <option key={r} value={r}>
                        {r} miles
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              <Field label="Working hours">
                <div className="flex items-center gap-2">
                  <input
                    type="time"
                    value={workStart}
                    onChange={(e) => {
                      setWorkStart(e.target.value);
                      touch();
                    }}
                    className={inputClass}
                  />
                  <span className="text-navy-400">—</span>
                  <input
                    type="time"
                    value={workEnd}
                    onChange={(e) => {
                      setWorkEnd(e.target.value);
                      touch();
                    }}
                    className={inputClass}
                  />
                </div>
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Meeting duration">
                  <select
                    value={duration}
                    onChange={(e) => {
                      setDuration(Number(e.target.value));
                      touch();
                    }}
                    className={inputClass}
                  >
                    {Array.from(new Set([...DURATION_OPTIONS, duration])).sort((a, b) => a - b).map((d) => (
                      <option key={d} value={d}>
                        {d} min
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Arrival buffer" hint="Parking / check-in before each meeting">
                  <select
                    value={buffer}
                    onChange={(e) => {
                      setBuffer(Number(e.target.value));
                      touch();
                    }}
                    className={inputClass}
                  >
                    {Array.from(new Set([0, 5, 10, 15, buffer])).sort((a, b) => a - b).map((b) => (
                      <option key={b} value={b}>
                        {b === 0 ? "None" : `${b} min`}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              <label className="flex cursor-pointer items-center gap-2 text-sm text-navy-700">
                <input
                  type="checkbox"
                  checked={allowOvertime}
                  onChange={(e) => {
                    setAllowOvertime(e.target.checked);
                    touch();
                  }}
                  className="h-4 w-4 accent-teal-600"
                />
                Allow meetings past working hours
              </label>

              <Field label="Route name (optional)">
                <input
                  value={routeName}
                  onChange={(e) => setRouteName(e.target.value)}
                  placeholder="e.g. Wilson healthcare day"
                  className={inputClass}
                />
              </Field>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="text-sm font-semibold text-navy-900">Prospects</h2>
              {isAdmin && (
                <select
                  value={scope}
                  onChange={(e) => setScope(e.target.value as "assigned" | "all")}
                  className="rounded-md border border-navy-200 px-2 py-1 text-xs text-navy-700"
                >
                  <option value="assigned">Assigned to salesperson</option>
                  <option value="all">All companies</option>
                </select>
              )}
            </CardHeader>
            <CardBody>
              <ProspectPicker
                data={candidates}
                loading={candLoading}
                error={candError}
                selectedIds={selectedSet}
                onToggle={toggle}
                onSelectMany={selectMany}
                onPriorityChange={changePriority}
                onLocate={locate}
                locatingIds={locatingIds}
                activeCompanyId={activeCompanyId}
                onFocus={setActiveCompanyId}
              />
              <Button className="mt-4 w-full" size="lg" disabled={!canGenerate} onClick={() => runPlan(true)}>
                {planning === "optimize" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {planning === "optimize"
                  ? "Optimizing…"
                  : `Generate Optimized Route${selectedIds.length ? ` (${selectedIds.length})` : ""}`}
              </Button>
              {!start && <p className="mt-2 text-center text-xs text-navy-500">Choose a start location first.</p>}
            </CardBody>
          </Card>

          <SavedRoutesCard
            routes={savedRoutes}
            activeId={savedRouteId}
            showSalesperson={false}
            onOpen={openSaved}
            onDelete={setConfirmDelete}
          />
        </div>

        {/* ------------------------------------------------ right: map, summary, timeline */}
        <div className="min-w-0 space-y-5">
          <div className="h-[460px] overflow-hidden rounded-xl border border-navy-100 bg-white shadow-card">
            <RoutePlannerMap
              start={start}
              end={savedEnd}
              endIsStart={plan?.config.end_mode === "same_as_start"}
              stops={shownStops}
              candidates={candidates?.candidates ?? []}
              selectedIds={selectedSet}
              geometry={plan && !dirty ? plan.geometry : null}
              radiusMiles={radius}
              activeCompanyId={activeCompanyId}
              onSelectCompany={setActiveCompanyId}
              onOpenDetails={setDrawerCompanyId}
              stale={dirty}
            />
          </div>

          {planError && <PlanErrorBanner error={planError} onLocate={locate} onRemove={(ids) => selectMany(ids, false)} />}

          {stale && savedRouteId && !dirty && (
            <Banner tone="warning" icon={AlertTriangle}>
              <span className="flex-1">
                Some company locations changed since this route was saved. The saved plan is shown unchanged.
              </span>
              <Button size="sm" variant="secondary" onClick={recalculateSaved} disabled={!!planning}>
                <RefreshCw className="h-3.5 w-3.5" /> Recalculate
              </Button>
            </Banner>
          )}

          {plan && dirty && (
            <Banner tone="info" icon={RefreshCw}>
              <span className="flex-1">The route changed. Recalculate to update travel times and the schedule.</span>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => runPlan(true)} disabled={!canGenerate}>
                  <Sparkles className="h-3.5 w-3.5" /> Re-optimize
                </Button>
                <Button size="sm" onClick={() => runPlan(false)} disabled={!canGenerate}>
                  {planning === "recalculate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                  Recalculate Route
                </Button>
              </div>
            </Banner>
          )}

          {plan && !dirty && plan.warnings.length > 0 && (
            <div className="space-y-2">
              {plan.warnings.map((w) => (
                <Banner key={w} tone="warning" icon={AlertTriangle}>
                  {w}
                </Banner>
              ))}
            </div>
          )}

          {plan ? (
            <>
              <PlanSummary plan={plan} dimmed={dirty} />
              <Card>
                <CardHeader>
                  <div>
                    <h2 className="text-sm font-semibold text-navy-900">Timeline · {formatDate(plan.config.date)}</h2>
                    <p className="text-xs text-navy-500">
                      Drag stops (or use the arrows) to reorder, then recalculate.
                      {!dirty && plan.optimization_engine !== "manual" && (
                        <> Order optimized {plan.optimization_engine === "geoapify_route_planner" ? "by Geoapify Route Planner" : "in-app"} using {ENGINE_LABELS[plan.routing_engine] ?? plan.routing_engine} road travel times.</>
                      )}
                    </p>
                  </div>
                  <Button className="shrink-0 whitespace-nowrap" onClick={() => save()} disabled={dirty || saving || plan.stops.length === 0}>
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {savedRouteId ? "Save Changes" : "Save Route"}
                  </Button>
                </CardHeader>
                <CardBody>
                  <PlanTimeline
                    plan={plan}
                    orderIds={selectedIds}
                    dirty={dirty}
                    candidatesById={candidatesById}
                    durations={durations}
                    defaultDuration={duration}
                    editable
                    activeCompanyId={activeCompanyId}
                    onSelect={setActiveCompanyId}
                    onOpenDetails={setDrawerCompanyId}
                    onReorder={(ids) => {
                      setSelectedIds(ids);
                      setDirty(true);
                    }}
                    onRemove={(id) => {
                      setSelectedIds((prev) => prev.filter((x) => x !== id));
                      setDirty(true);
                    }}
                    onDurationChange={(id, minutes) => {
                      setDurations((prev) => ({ ...prev, [id]: minutes }));
                      setDirty(true);
                    }}
                  />
                </CardBody>
              </Card>
            </>
          ) : (
            <EmptyState
              icon={<MapPinned className="h-5 w-5" />}
              title="No route yet"
              description="Select prospects on the left and click Generate Optimized Route. Travel times come from real road routes."
            />
          )}
        </div>
      </div>

      <ProspectDrawer
        companyId={drawerCompanyId}
        assignedUserId={drawerCompanyId ? candidatesById.get(drawerCompanyId)?.assigned_user_id ?? null : null}
        onClose={() => setDrawerCompanyId(null)}
        salespeople={salespeople}
        onChanged={loadCandidates}
      />
      <ConfirmDialog
        open={!!confirmReplace}
        title="Replace the existing route?"
        description={
          confirmReplace
            ? `A route is already saved for ${formatDate(confirmReplace.date)} (${confirmReplace.stop_count} stops). Saving replaces it and updates that day's planned meetings.`
            : undefined
        }
        confirmLabel="Replace route"
        onCancel={() => setConfirmReplace(null)}
        onConfirm={() => {
          const target = confirmReplace;
          setConfirmReplace(null);
          if (target) {
            setSavedRouteId(target.id);
            setSaving(true);
            routePlannerApi
              .update(target.id, { plan: { ...plan!, config: { ...plan!.config, name: routeName.trim() || null } } })
              .then(async (saved) => {
                setPlan(saved);
                setSavedStatus(saved.status);
                await loadSavedRoutes();
                toast({ title: "Route saved", variant: "success" });
              })
              .catch((err) => toast({ title: "Couldn't save route", description: err.message, variant: "error" }))
              .finally(() => setSaving(false));
          }
        }}
      />
      <ConfirmDialog
        open={!!confirmDelete}
        title="Delete this route?"
        description="Planned (unconfirmed) meetings created for this route are removed too. Meetings booked by hand are kept."
        confirmLabel="Delete"
        danger
        onCancel={() => setConfirmDelete(null)}
        onConfirm={() => {
          const target = confirmDelete;
          setConfirmDelete(null);
          if (target) deleteSaved(target);
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------

const inputClass =
  "w-full rounded-lg border border-navy-200 bg-white px-2.5 py-1.5 text-sm text-navy-800 outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-navy-600" title={hint}>
        {label}
      </label>
      {children}
    </div>
  );
}

function IconBtn({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg border border-navy-200 text-navy-500 transition-colors hover:bg-navy-50 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function Banner({
  tone,
  icon: Icon,
  children,
}: {
  tone: "warning" | "info" | "danger";
  icon: typeof AlertTriangle;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm",
        tone === "warning" && "border-amber-200 bg-amber-50 text-amber-900",
        tone === "info" && "border-teal-200 bg-teal-50 text-teal-900",
        tone === "danger" && "border-red-200 bg-red-50 text-red-900"
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {children}
    </div>
  );
}

function PlanErrorBanner({
  error,
  onLocate,
  onRemove,
}: {
  error: PlanErrorState;
  onLocate: (ids: string[]) => void;
  onRemove: (ids: string[]) => void;
}) {
  const ids = error.companies.map((c) => c.company_id);
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
      <p className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-4 w-4 shrink-0" /> {error.message}
      </p>
      {error.companies.length > 0 && (
        <>
          <ul className="mt-2 space-y-0.5 pl-6 text-xs">
            {error.companies.map((c) => (
              <li key={c.company_id}>
                <span className="font-medium">{c.company_name}</span>
                {c.address ? ` — ${c.address}` : ""}
              </li>
            ))}
          </ul>
          {error.code === "missing_coordinates" && (
            <div className="mt-2.5 flex gap-2 pl-6">
              <Button size="sm" variant="secondary" onClick={() => onLocate(ids)}>
                <LocateFixed className="h-3.5 w-3.5" /> Try to locate them
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onRemove(ids)}>
                Remove from selection
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PlanSummary({ plan, dimmed }: { plan: RoutePlan; dimmed: boolean }) {
  const stats = [
    { icon: RouteIcon, label: "Total distance", value: formatMiles(plan.total_distance_meters) },
    { icon: Car, label: "Driving time", value: formatDuration(plan.total_driving_seconds) },
    { icon: Timer, label: "Meeting time", value: formatDuration(plan.total_meeting_seconds) },
    {
      icon: Clock,
      label: "Total day",
      value: formatDuration(plan.total_duration_seconds),
      sub: `${formatClock(plan.day_start)} – ${formatClock(plan.day_finish)}`,
    },
    {
      icon: CalendarDays,
      label: "Meetings",
      value: `${plan.scheduled_count}${plan.selected_count !== plan.scheduled_count ? ` of ${plan.selected_count}` : ""}`,
    },
  ];
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5", dimmed && "opacity-50")}>
      {stats.map((s) => (
        <div key={s.label} className="rounded-xl border border-navy-100 bg-white px-4 py-3 shadow-card">
          <p className="flex items-center gap-1.5 text-xs font-medium text-navy-500">
            <s.icon className="h-3.5 w-3.5 text-teal-600" />
            {s.label}
          </p>
          <p className="mt-1 text-lg font-semibold text-navy-900">{s.value}</p>
          {s.sub && <p className="text-xs text-navy-500">{s.sub}</p>}
        </div>
      ))}
    </div>
  );
}

function SavedRoutesCard({
  routes,
  activeId,
  showSalesperson,
  onOpen,
  onDelete,
}: {
  routes: RouteListItem[];
  activeId: string | null;
  showSalesperson: boolean;
  onOpen: (id: string) => void;
  onDelete: (item: RouteListItem) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <h2 className="text-sm font-semibold text-navy-900">Saved routes</h2>
        <span className="text-xs text-navy-500">{routes.length}</span>
      </CardHeader>
      <CardBody className="p-2">
        {routes.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-navy-400">No saved routes yet.</p>
        ) : (
          <ul className="scrollbar-thin max-h-72 space-y-0.5 overflow-y-auto">
            {routes.map((r) => (
              <li
                key={r.id}
                className={cn(
                  "group flex items-center gap-2 rounded-lg px-3 py-2 transition-colors",
                  r.id === activeId ? "bg-teal-50" : "hover:bg-navy-50"
                )}
              >
                <button type="button" onClick={() => onOpen(r.id)} className="min-w-0 flex-1 text-left">
                  <p className="truncate text-sm font-medium text-navy-800">{r.name || formatDate(r.date)}</p>
                  <p className="truncate text-xs text-navy-500">
                    {r.name ? `${formatDate(r.date)} · ` : ""}
                    {r.stop_count} stops
                    {r.total_distance_meters ? ` · ${formatMiles(r.total_distance_meters)}` : ""}
                    {showSalesperson && r.salesperson_name ? ` · ${r.salesperson_name}` : ""}
                  </p>
                </button>
                <button
                  type="button"
                  title="Delete route"
                  aria-label="Delete route"
                  onClick={() => onDelete(r)}
                  className="rounded-md p-1 text-navy-300 opacity-0 transition hover:text-danger group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
