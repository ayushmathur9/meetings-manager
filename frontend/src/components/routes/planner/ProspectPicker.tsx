"use client";

import { useMemo, useState } from "react";
import { Loader2, LocateFixed, MapPinOff, Search } from "lucide-react";
import type { CandidatesOut, ProspectPriority, RadiusStatus, RouteCandidate } from "@/types";
import { cn } from "@/lib/utils";
import { formatClock, PRIORITY_STYLES } from "./format";

const TABS: { key: RadiusStatus; label: string }[] = [
  { key: "inside", label: "In radius" },
  { key: "outside", label: "Outside" },
  { key: "missing_coordinates", label: "No location" },
];

const PRIORITY_ORDER: ProspectPriority[] = ["high", "medium", "low"];

export function ProspectPicker({
  data,
  loading,
  error,
  selectedIds,
  onToggle,
  onSelectMany,
  onPriorityChange,
  onLocate,
  locatingIds,
  activeCompanyId,
  onFocus,
}: {
  data: CandidatesOut | null;
  loading: boolean;
  error: string | null;
  selectedIds: Set<string>;
  onToggle: (companyId: string) => void;
  onSelectMany: (companyIds: string[], selected: boolean) => void;
  onPriorityChange: (companyId: string, priority: ProspectPriority) => void;
  onLocate: (companyIds: string[]) => void;
  locatingIds: Set<string>;
  activeCompanyId: string | null;
  onFocus: (companyId: string) => void;
}) {
  const [tab, setTab] = useState<RadiusStatus>("inside");
  const [search, setSearch] = useState("");

  const counts: Record<RadiusStatus, number> = {
    inside: data?.inside_count ?? 0,
    outside: data?.outside_count ?? 0,
    missing_coordinates: data?.missing_count ?? 0,
  };

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.candidates ?? []).filter(
      (c) =>
        c.radius_status === tab &&
        (!q || c.company_name.toLowerCase().includes(q) || (c.address ?? "").toLowerCase().includes(q) || (c.industry ?? "").toLowerCase().includes(q))
    );
  }, [data, tab, search]);

  const selectable = visible.filter((c) => c.radius_status === "inside");
  const allVisibleSelected = selectable.length > 0 && selectable.every((c) => selectedIds.has(c.company_id));

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-3">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-navy-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Finding prospects…
          </p>
        ) : error ? (
          <p className="text-sm text-danger">{error}</p>
        ) : data ? (
          <p className="text-sm text-navy-700">
            <span className="text-lg font-semibold text-navy-900">{data.inside_count}</span> prospect
            {data.inside_count === 1 ? "" : "s"} found within {data.radius_miles} miles
          </p>
        ) : (
          <p className="text-sm text-navy-500">Choose a start location to find prospects.</p>
        )}
      </div>

      <div className="mb-2 flex rounded-lg bg-navy-50 p-0.5 text-xs font-medium">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 transition-colors",
              tab === t.key ? "bg-white text-navy-900 shadow-sm" : "text-navy-500 hover:text-navy-800"
            )}
          >
            {t.label}
            <span
              className={cn(
                "rounded-full px-1.5 text-[10px]",
                t.key === "missing_coordinates" && counts[t.key] > 0 ? "bg-amber-100 text-warning" : "bg-navy-100 text-navy-600"
              )}
            >
              {counts[t.key]}
            </span>
          </button>
        ))}
      </div>

      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search prospects…"
          className="w-full rounded-lg border border-navy-200 py-1.5 pl-8 pr-2 text-sm outline-none focus:border-teal-500 focus-visible:shadow-focus-ring"
        />
      </div>

      <div className="mb-1 flex items-center justify-between px-1 text-xs text-navy-500">
        {tab === "missing_coordinates" ? (
          <>
            <span>These can&apos;t be routed until they have a location.</span>
            {visible.length > 0 && (
              <button
                type="button"
                onClick={() => onLocate(visible.map((c) => c.company_id))}
                className="font-medium text-teal-700 hover:text-teal-800"
              >
                Locate all
              </button>
            )}
          </>
        ) : tab === "outside" ? (
          <span>Outside the radius. Increase the radius to include these.</span>
        ) : (
          <>
            <span>{selectedIds.size} selected</span>
            {selectable.length > 0 && (
              <button
                type="button"
                onClick={() => onSelectMany(selectable.map((c) => c.company_id), !allVisibleSelected)}
                className="font-medium text-teal-700 hover:text-teal-800"
              >
                {allVisibleSelected ? "Clear" : "Select all"}
              </button>
            )}
          </>
        )}
      </div>

      <ul className="scrollbar-thin -mx-1 max-h-[340px] min-h-[120px] space-y-0.5 overflow-y-auto px-1">
        {visible.length === 0 && !loading && (
          <li className="flex flex-col items-center gap-1 py-8 text-center text-xs text-navy-400">
            <MapPinOff className="h-4 w-4" />
            {tab === "inside" ? "No prospects in this radius." : "Nothing here."}
          </li>
        )}
        {visible.map((c) => (
          <CandidateRow
            key={c.company_id}
            candidate={c}
            selected={selectedIds.has(c.company_id)}
            active={activeCompanyId === c.company_id}
            locating={locatingIds.has(c.company_id)}
            onToggle={() => onToggle(c.company_id)}
            onPriority={(p) => onPriorityChange(c.company_id, p)}
            onLocate={() => onLocate([c.company_id])}
            onFocus={() => onFocus(c.company_id)}
          />
        ))}
      </ul>
    </div>
  );
}

function CandidateRow({
  candidate: c,
  selected,
  active,
  locating,
  onToggle,
  onPriority,
  onLocate,
  onFocus,
}: {
  candidate: RouteCandidate;
  selected: boolean;
  active: boolean;
  locating: boolean;
  onToggle: () => void;
  onPriority: (p: ProspectPriority) => void;
  onLocate: () => void;
  onFocus: () => void;
}) {
  const missing = c.radius_status === "missing_coordinates";
  const selectable = c.radius_status === "inside";
  return (
    <li
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2 py-2 transition-colors",
        active ? "bg-teal-50" : "hover:bg-navy-50"
      )}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={!selectable}
        onChange={onToggle}
        aria-label={`Select ${c.company_name}`}
        className="h-4 w-4 shrink-0 rounded border-navy-300 accent-teal-600 disabled:opacity-30"
      />
      <button type="button" onClick={onFocus} className="min-w-0 flex-1 text-left">
        <span className="block truncate text-sm font-medium text-navy-800">{c.company_name}</span>
        <span className="block truncate text-xs text-navy-500">
          {c.distance_miles != null ? `${c.distance_miles.toFixed(1)} mi · ` : ""}
          {c.address || "No address on file"}
        </span>
        {c.existing_meeting_time && (
          <span className="mt-0.5 block text-[11px] font-medium text-teal-700">
            {c.existing_meeting_fixed ? "Meeting booked" : "Planned"} · {formatClock(c.existing_meeting_time)}
          </span>
        )}
      </button>
      {missing ? (
        <button
          type="button"
          onClick={onLocate}
          disabled={locating}
          className="flex shrink-0 items-center gap-1 rounded-md border border-navy-200 px-2 py-1 text-xs font-medium text-navy-700 hover:bg-white disabled:opacity-50"
        >
          {locating ? <Loader2 className="h-3 w-3 animate-spin" /> : <LocateFixed className="h-3 w-3" />}
          Locate
        </button>
      ) : (
        <select
          aria-label={`Priority for ${c.company_name}`}
          value={c.priority}
          onChange={(e) => onPriority(e.target.value as ProspectPriority)}
          className={cn(
            "shrink-0 cursor-pointer appearance-none rounded-full px-2 py-0.5 text-center text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset outline-none",
            PRIORITY_STYLES[c.priority].className
          )}
        >
          {PRIORITY_ORDER.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_STYLES[p].label}
            </option>
          ))}
        </select>
      )}
    </li>
  );
}
