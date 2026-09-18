"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, Users as UsersIcon, X } from "lucide-react";
import { prospectsApi, ProspectFilterParams } from "@/lib/api/prospects";
import { usersApi } from "@/lib/api/users";
import type { ProspectListItem, User } from "@/types";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProspectMap, MapMarkerPoint } from "@/components/map/ProspectMap";
import { ProspectDrawer } from "@/components/prospects/ProspectDrawer";
import { CompanyCard } from "@/components/companies/CompanyCard";
import { FilterBar, FilterField, filterInputClass } from "@/components/prospects/FilterBar";
import { PageHeader } from "@/components/layout/PageHeader";
import { useToast } from "@/components/ui/Toast";

const RADIUS_OPTIONS = [1, 5, 10, 25, 50];
const STATUS_OPTIONS = [
  "new",
  "researched",
  "contacted",
  "meeting",
  "follow_up",
  "not_interested",
  "not_a_fit",
  "existing_customer",
];

const VERIFICATION_OPTIONS = ["verified", "needs_review", "unverified", "failed"];

export default function AdminProspectsPage() {
  const toast = useToast();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<ProspectListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [industry, setIndustry] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [assignedFilter, setAssignedFilter] = useState("");
  const [radiusMiles, setRadiusMiles] = useState<number | "">("");
  const [centerLat, setCenterLat] = useState("");
  const [centerLng, setCenterLng] = useState("");
  const [verificationFilter, setVerificationFilter] = useState(
    () => searchParams.get("verification_status") || ""
  );

  const load = useCallback(async () => {
    setLoading(true);
    const params: ProspectFilterParams = {
      search: search || undefined,
      industry: industry || undefined,
      status: statusFilter || undefined,
      unassigned_only: assignedFilter === "unassigned",
      assigned_user_id: assignedFilter && assignedFilter !== "unassigned" ? assignedFilter : undefined,
      verification_status: verificationFilter || undefined,
      page_size: 200,
    };
    if (radiusMiles && centerLat && centerLng) {
      params.radius_miles = Number(radiusMiles);
      params.center_lat = Number(centerLat);
      params.center_lng = Number(centerLng);
    }
    try {
      const page = await prospectsApi.list(params);
      setItems(page.items);
      setTotal(page.total);
    } finally {
      setLoading(false);
    }
  }, [search, industry, statusFilter, assignedFilter, radiusMiles, centerLat, centerLng, verificationFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    usersApi.list().then((u) => setUsers(u.filter((x) => x.role === "salesperson")));
  }, []);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleBulkAssign(userId: string) {
    if (!userId || selected.size === 0) return;
    const count = selected.size;
    await prospectsApi.bulkAssign(Array.from(selected), userId);
    const person = users.find((u) => u.id === userId);
    toast({
      title: `${count} prospect${count === 1 ? "" : "s"} assigned`,
      description: person ? `Assigned to ${person.name}` : undefined,
      variant: "success",
    });
    setSelected(new Set());
    load();
  }

  const markers: MapMarkerPoint[] = items
    .filter((i) => i.latitude && i.longitude)
    .map((i) => ({
      id: i.company_id,
      lat: i.latitude!,
      lng: i.longitude!,
      label: i.company_name,
      status:
        i.verification_status !== "verified" && i.verification_status !== null
          ? "needs_verification"
          : i.next_meeting_date
          ? "scheduled"
          : i.assigned_user_id
          ? "assigned"
          : "unassigned",
    }));

  return (
    <div className="flex h-full flex-col p-6 pb-0">
      <PageHeader title="Prospects" description={`${total} companies match your filters`} />

      <FilterBar className="mb-4">
        <FilterField label="Search">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Company, industry, phone"
              className={`${filterInputClass} w-52 pl-8`}
            />
          </div>
        </FilterField>
        <FilterField label="Industry">
          <input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="Healthcare"
            className={`${filterInputClass} w-36`}
          />
        </FilterField>
        <FilterField label="Status">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={filterInputClass}>
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Location">
          <select
            value={verificationFilter}
            onChange={(e) => setVerificationFilter(e.target.value)}
            className={filterInputClass}
          >
            <option value="">Any</option>
            {VERIFICATION_OPTIONS.map((v) => (
              <option key={v} value={v}>
                {v.replace("_", " ")}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Assigned to">
          <select value={assignedFilter} onChange={(e) => setAssignedFilter(e.target.value)} className={filterInputClass}>
            <option value="">Anyone</option>
            <option value="unassigned">Unassigned</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Radius (from lat,lng)">
          <div className="flex gap-1">
            <input
              value={centerLat}
              onChange={(e) => setCenterLat(e.target.value)}
              placeholder="lat"
              className={`${filterInputClass} w-20`}
            />
            <input
              value={centerLng}
              onChange={(e) => setCenterLng(e.target.value)}
              placeholder="lng"
              className={`${filterInputClass} w-20`}
            />
            <select
              value={radiusMiles}
              onChange={(e) => setRadiusMiles(e.target.value ? Number(e.target.value) : "")}
              className={filterInputClass}
            >
              <option value="">Any</option>
              {RADIUS_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {r} mi
                </option>
              ))}
            </select>
          </div>
        </FilterField>
      </FilterBar>

      <div className="relative flex flex-1 gap-4 overflow-hidden pb-6">
        <div className="scrollbar-thin w-1/2 space-y-2 overflow-y-auto pb-16 pr-1">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <LoadingSkeleton key={i} className="h-20 w-full" />)
          ) : items.length === 0 ? (
            <EmptyState
              icon={<UsersIcon className="h-5 w-5" />}
              title="No prospects match these filters"
              description="Try widening your search, or import a prospect list to get started."
            />
          ) : (
            items.map((item) => (
              <CompanyCard
                key={item.company_id}
                item={item}
                selected={selected.has(item.company_id)}
                onSelect={toggleSelect}
                onOpen={setActiveCompanyId}
              />
            ))
          )}
        </div>
        <div className="w-1/2 pb-2">
          <ProspectMap
            markers={markers}
            onMarkerClick={setActiveCompanyId}
            selectedId={activeCompanyId ?? undefined}
            cluster
          />
        </div>

        {selected.size > 0 && (
          <div className="absolute bottom-4 left-0 right-1/2 mr-2 flex items-center gap-3 rounded-xl border border-navy-100 bg-white px-4 py-3 shadow-dropdown">
            <span className="text-sm font-medium text-navy-800">{selected.size} selected</span>
            <select
              onChange={(e) => handleBulkAssign(e.target.value)}
              defaultValue=""
              className={filterInputClass}
            >
              <option value="" disabled>
                Assign to...
              </option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
            <button
              className="ml-auto flex items-center gap-1 text-sm text-navy-500 hover:text-navy-800"
              onClick={() => setSelected(new Set())}
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </button>
          </div>
        )}
      </div>

      <ProspectDrawer
        companyId={activeCompanyId}
        assignedUserId={items.find((i) => i.company_id === activeCompanyId)?.assigned_user_id}
        onClose={() => setActiveCompanyId(null)}
        salespeople={users}
        onChanged={load}
      />
    </div>
  );
}
