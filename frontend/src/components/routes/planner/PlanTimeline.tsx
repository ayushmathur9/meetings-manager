"use client";

import { useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ChevronDown,
  ChevronUp,
  Clock,
  Flag,
  GripVertical,
  Home,
  Info,
  Navigation as NavigationIcon,
  X,
} from "lucide-react";
import type { PlannedStop, RouteCandidate, RoutePlan } from "@/types";
import { cn } from "@/lib/utils";
import { formatClock, formatDuration, formatMiles, navigationUrl, PRIORITY_STYLES } from "./format";

const DURATION_OPTIONS = [15, 20, 25, 30, 45, 60];

export function PriorityPill({ priority, className }: { priority: PlannedStop["priority"]; className?: string }) {
  const style = PRIORITY_STYLES[priority];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset",
        style.className,
        className
      )}
    >
      {style.label}
    </span>
  );
}

interface Row {
  companyId: string;
  name: string;
  address: string | null;
  priority: PlannedStop["priority"];
  stop: PlannedStop | null; // null = newly added, not scheduled yet
}

export function PlanTimeline({
  plan,
  orderIds,
  dirty,
  candidatesById,
  durations,
  defaultDuration,
  editable,
  activeCompanyId,
  onSelect,
  onOpenDetails,
  onReorder,
  onRemove,
  onDurationChange,
}: {
  plan: RoutePlan;
  orderIds: string[];
  dirty: boolean;
  candidatesById: Map<string, RouteCandidate>;
  durations: Record<string, number>;
  defaultDuration: number;
  editable: boolean;
  activeCompanyId: string | null;
  onSelect: (companyId: string) => void;
  onOpenDetails: (companyId: string) => void;
  onReorder: (ids: string[]) => void;
  onRemove: (companyId: string) => void;
  onDurationChange: (companyId: string, minutes: number) => void;
}) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const stopsById = new Map(plan.stops.map((s) => [s.company_id, s]));
  const unscheduledIds = new Set(plan.unscheduled.map((u) => u.company_id));

  // Clean plan: show exactly what was computed. Edited plan: show the user's
  // working order, with times greyed out until they recalculate.
  const rowIds = dirty ? orderIds : plan.stops.map((s) => s.company_id);
  const rows: Row[] = rowIds
    .filter((id) => dirty || !unscheduledIds.has(id))
    .map((id) => {
      const stop = stopsById.get(id) ?? null;
      const candidate = candidatesById.get(id);
      return {
        companyId: id,
        name: stop?.company_name ?? candidate?.company_name ?? "Prospect",
        address: stop?.address ?? candidate?.address ?? null,
        priority: stop?.priority ?? candidate?.priority ?? "medium",
        stop,
      };
    });

  function move(id: string, delta: number) {
    const ids = rows.map((r) => r.companyId);
    const index = ids.indexOf(id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    onReorder([...ids, ...orderIds.filter((x) => !ids.includes(x))]);
  }

  function drop(targetId: string) {
    if (!dragId || dragId === targetId) return;
    const ids = rows.map((r) => r.companyId).filter((x) => x !== dragId);
    ids.splice(ids.indexOf(targetId), 0, dragId);
    onReorder([...ids, ...orderIds.filter((x) => !ids.includes(x))]);
  }

  const start = plan.config.start_location;
  const end = plan.config.end_mode === "same_as_start" ? start : plan.config.end_mode === "custom" ? plan.config.end_location : null;

  return (
    <div>
      <ol className="relative">
        {/* Start */}
        <li className="flex items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-900 text-white">
            <Home className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-navy-900">{start.name}</p>
            <p className="text-xs text-navy-500">Depart {formatClock(plan.day_start)}</p>
          </div>
        </li>

        {rows.map((row, i) => {
          const stop = row.stop;
          const duration = durations[row.companyId] ?? stop?.duration_minutes ?? defaultDuration;
          const isActive = activeCompanyId === row.companyId;
          return (
            <li key={row.companyId}>
              <Leg
                text={
                  stop && !dirty
                    ? `${formatDuration(stop.travel_time_seconds)} · ${formatMiles(stop.distance_meters)}`
                    : "Recalculate to update drive time"
                }
                muted={dirty}
              />
              <div
                draggable={editable}
                onDragStart={() => setDragId(row.companyId)}
                onDragEnd={() => {
                  setDragId(null);
                  setOverId(null);
                }}
                onDragOver={(e) => {
                  if (!editable) return;
                  e.preventDefault();
                  setOverId(row.companyId);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  drop(row.companyId);
                  setOverId(null);
                }}
                onClick={() => onSelect(row.companyId)}
                className={cn(
                  "group flex cursor-pointer gap-3 rounded-xl border bg-white p-3 shadow-card transition",
                  isActive ? "border-teal-400 ring-2 ring-teal-100" : "border-navy-100 hover:border-navy-200",
                  overId === row.companyId && dragId !== row.companyId && "border-teal-500 border-dashed",
                  dragId === row.companyId && "opacity-50"
                )}
              >
                <div className="flex flex-col items-center gap-1">
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold text-white",
                      !stop || dirty ? "bg-navy-300" : stop.outside_hours || stop.late_seconds ? "bg-warning" : "bg-teal-600"
                    )}
                  >
                    {i + 1}
                  </span>
                  {editable && (
                    <GripVertical className="h-4 w-4 cursor-grab text-navy-300 group-hover:text-navy-500" aria-hidden />
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-navy-900">{row.name}</p>
                      {row.address && <p className="truncate text-xs text-navy-500">{row.address}</p>}
                    </div>
                    <PriorityPill priority={row.priority} className="shrink-0" />
                  </div>

                  {stop ? (
                    <div className={cn("mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs", dirty && "opacity-40")}>
                      <p className="text-navy-500">
                        Arrive <span className="font-semibold text-navy-800">{formatClock(stop.arrival_time)}</span>
                      </p>
                      <p className="text-navy-500">
                        Meeting{" "}
                        <span className="font-semibold text-navy-800">
                          {formatClock(stop.meeting_start)}–{formatClock(stop.meeting_end)}
                        </span>
                      </p>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs italic text-navy-400">New stop — recalculate to schedule it.</p>
                  )}

                  {stop && !dirty && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {stop.is_fixed_time && <Note icon={Clock} tone="info">Scheduled meeting time kept</Note>}
                      {stop.wait_seconds > 0 && <Note icon={Clock} tone="info">{formatDuration(stop.wait_seconds)} wait</Note>}
                      {stop.late_seconds > 0 && (
                        <Note icon={AlertTriangle} tone="warning">{formatDuration(stop.late_seconds)} late</Note>
                      )}
                      {stop.outside_hours && <Note icon={AlertTriangle} tone="warning">After working hours</Note>}
                      {stop.outside_radius && <Note icon={Info} tone="neutral">Outside radius</Note>}
                      {stop.location_changed && (
                        <Note icon={AlertTriangle} tone="warning">Location changed since saved</Note>
                      )}
                    </div>
                  )}

                  {stop?.contact_name && <p className="mt-1.5 text-xs text-navy-500">Contact: {stop.contact_name}</p>}

                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {stop?.latitude != null && stop?.longitude != null && (
                      <a
                        href={navigationUrl(stop.latitude, stop.longitude)}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-md bg-navy-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-navy-800"
                      >
                        <NavigationIcon className="h-3 w-3" /> Navigate
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => onOpenDetails(row.companyId)}
                      className="rounded-md border border-navy-200 px-2.5 py-1 text-xs font-medium text-navy-700 hover:bg-navy-50"
                    >
                      Details
                    </button>
                    {editable && (
                      <>
                        <select
                          aria-label="Meeting duration"
                          value={duration}
                          onChange={(e) => onDurationChange(row.companyId, Number(e.target.value))}
                          className="rounded-md border border-navy-200 bg-white px-1.5 py-1 text-xs text-navy-700"
                        >
                          {Array.from(new Set([...DURATION_OPTIONS, duration])).sort((a, b) => a - b).map((d) => (
                            <option key={d} value={d}>
                              {d} min
                            </option>
                          ))}
                        </select>
                        <div className="ml-auto flex items-center gap-0.5">
                          <IconButton label="Move up" disabled={i === 0} onClick={() => move(row.companyId, -1)}>
                            <ChevronUp className="h-3.5 w-3.5" />
                          </IconButton>
                          <IconButton label="Move down" disabled={i === rows.length - 1} onClick={() => move(row.companyId, 1)}>
                            <ChevronDown className="h-3.5 w-3.5" />
                          </IconButton>
                          <IconButton label="Remove stop" danger onClick={() => onRemove(row.companyId)}>
                            <X className="h-3.5 w-3.5" />
                          </IconButton>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </li>
          );
        })}

        {/* End */}
        {end ? (
          <li>
            <Leg
              text={
                dirty
                  ? "Recalculate to update drive time"
                  : `${formatDuration(plan.return_travel_seconds)} · ${formatMiles(plan.return_distance_meters)}`
              }
              muted={dirty}
            />
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-600 text-white">
                <Flag className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-navy-900">
                  {plan.config.end_mode === "same_as_start" ? `Return to ${end.name}` : end.name}
                </p>
                <p className="text-xs text-navy-500">Arrive {dirty ? "—" : formatClock(plan.day_finish)}</p>
              </div>
            </div>
          </li>
        ) : (
          rows.length > 0 && (
            <li className="mt-3 pl-11 text-xs text-navy-500">
              No fixed end · day finishes at {dirty ? "—" : formatClock(plan.day_finish)}
            </li>
          )
        )}
      </ol>

      {!dirty && plan.unscheduled.length > 0 && (
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50/70 p-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-warning">
            <AlertTriangle className="h-3.5 w-3.5" /> Not scheduled ({plan.unscheduled.length})
          </p>
          <ul className="space-y-1.5">
            {plan.unscheduled.map((u) => (
              <li key={u.company_id} className="flex items-center justify-between gap-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium text-navy-800">{u.company_name}</p>
                  <p className="text-xs text-navy-500">{u.message}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <PriorityPill priority={u.priority} />
                  {editable && (
                    <IconButton label="Remove from selection" danger onClick={() => onRemove(u.company_id)}>
                      <X className="h-3.5 w-3.5" />
                    </IconButton>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Leg({ text, muted }: { text: string; muted?: boolean }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="flex w-8 justify-center">
        <span className="h-6 border-l-2 border-dashed border-navy-200" />
      </span>
      <span className={cn("flex items-center gap-1 text-xs", muted ? "italic text-navy-300" : "text-navy-500")}>
        <ArrowDown className="h-3 w-3" />
        {text}
      </span>
    </div>
  );
}

function Note({
  icon: Icon,
  tone,
  children,
}: {
  icon: typeof Clock;
  tone: "info" | "warning" | "neutral";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
        tone === "warning" && "bg-amber-50 text-warning",
        tone === "info" && "bg-teal-50 text-teal-700",
        tone === "neutral" && "bg-navy-50 text-navy-500"
      )}
    >
      <Icon className="h-3 w-3" />
      {children}
    </span>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cn(
        "rounded-md p-1 text-navy-400 transition-colors hover:bg-navy-100 disabled:opacity-30",
        danger ? "hover:text-danger" : "hover:text-navy-800"
      )}
    >
      {children}
    </button>
  );
}
