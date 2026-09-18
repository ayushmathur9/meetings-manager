"use client";

import { useEffect, useState } from "react";
import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Badge, statusTone } from "@/components/ui/Badge";
import { LocationStatus } from "@/components/companies/LocationStatus";
import { ResolveLocationModal } from "@/components/companies/ResolveLocationModal";
import { companiesApi } from "@/lib/api/companies";
import { prospectsApi } from "@/lib/api/prospects";
import { navigationApi } from "@/lib/api/routes";
import type { CompanyOut, User } from "@/types";
import { ScheduleMeetingModal } from "@/components/meetings/ScheduleMeetingModal";
import { useToast } from "@/components/ui/Toast";
import { LoadingSkeleton } from "@/components/ui/Spinner";

export function ProspectDrawer({
  companyId,
  assignedUserId,
  onClose,
  salespeople,
  onChanged,
}: {
  companyId: string | null;
  assignedUserId?: string | null;
  onClose: () => void;
  salespeople: User[];
  onChanged: () => void;
}) {
  const toast = useToast();
  const [company, setCompany] = useState<CompanyOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [resolvingLocation, setResolvingLocation] = useState(false);
  const [currentAssignment, setCurrentAssignment] = useState(assignedUserId || "");

  useEffect(() => {
    setCurrentAssignment(assignedUserId || "");
  }, [assignedUserId, companyId]);

  useEffect(() => {
    if (!companyId) {
      setCompany(null);
      return;
    }
    setLoading(true);
    companiesApi
      .get(companyId)
      .then(setCompany)
      .finally(() => setLoading(false));
  }, [companyId]);

  async function handleAssign(userId: string) {
    if (!companyId) return;
    setCurrentAssignment(userId);
    await prospectsApi.assignSingle(companyId, userId || null);
    const person = salespeople.find((u) => u.id === userId);
    toast({
      title: "Assignment updated",
      description: person ? `Assigned to ${person.name}` : "Unassigned",
      variant: "success",
    });
    onChanged();
  }

  const primaryLocation = company?.locations[0] ?? null;

  async function handleNavigate() {
    if (!primaryLocation?.latitude || !primaryLocation?.longitude) return;
    try {
      const { url } = await navigationApi.getLink(primaryLocation.latitude, primaryLocation.longitude);
      const win = window.open(url, "_blank");
      if (!win) toast({ title: "Couldn't open navigation", description: "Check your popup blocker.", variant: "error" });
    } catch {
      toast({ title: "Couldn't open navigation", variant: "error" });
    }
  }

  return (
    <Drawer open={!!companyId} onClose={onClose} title={company?.name || "Loading..."}>
      {loading && (
        <div className="space-y-3">
          <LoadingSkeleton className="h-6 w-32" />
          <LoadingSkeleton className="h-24 w-full" />
          <LoadingSkeleton className="h-16 w-full" />
        </div>
      )}
      {company && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(company.status)}>{company.status.replace("_", " ")}</Badge>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">Location</h3>
            <LocationStatus
              location={primaryLocation}
              onNavigate={handleNavigate}
              onResolve={() => setResolvingLocation(true)}
            />
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">Company info</h3>
            <dl className="space-y-1 text-sm">
              <Row label="Industry" value={company.industry} />
              <Row label="Phone" value={company.phone} />
              <Row label="Website" value={company.website} />
              <Row label="Employees" value={company.employee_count?.toString()} />
            </dl>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">Contacts</h3>
            {company.contacts.length === 0 ? (
              <p className="text-sm text-navy-500">No contacts imported.</p>
            ) : (
              <ul className="space-y-2">
                {company.contacts.map((c) => (
                  <li key={c.id} className="rounded-lg border border-navy-100 p-2 text-sm">
                    <p className="font-medium text-navy-800">{c.full_name || "Unnamed contact"}</p>
                    <p className="text-navy-500">{c.title}</p>
                    <p className="text-navy-500">{c.email}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy-500">Assign salesperson</h3>
            <select
              value={currentAssignment}
              onChange={(e) => handleAssign(e.target.value)}
              className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none focus:border-teal-500 focus-visible:shadow-focus-ring"
            >
              <option value="">Unassigned</option>
              {salespeople.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>

          <Button className="w-full" onClick={() => setScheduling(true)}>
            Schedule meeting
          </Button>
        </div>
      )}

      {company && (
        <ScheduleMeetingModal
          open={scheduling}
          onClose={() => setScheduling(false)}
          company={company}
          salespeople={salespeople}
          onScheduled={() => {
            setScheduling(false);
            onChanged();
          }}
        />
      )}

      {companyId && (
        <ResolveLocationModal
          open={resolvingLocation}
          onClose={() => setResolvingLocation(false)}
          companyId={companyId}
          onResolved={() => {
            companiesApi.get(companyId).then(setCompany);
            onChanged();
          }}
        />
      )}
    </Drawer>
  );
}

function Row({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex justify-between border-b border-navy-50 py-1.5 last:border-0">
      <dt className="text-navy-500">{label}</dt>
      <dd className="text-navy-800">{value || "—"}</dd>
    </div>
  );
}
