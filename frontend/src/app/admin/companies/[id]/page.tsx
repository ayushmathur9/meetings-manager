"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Building2, Calendar, Navigation as NavigationIcon, Phone } from "lucide-react";
import { companiesApi } from "@/lib/api/companies";
import { usersApi } from "@/lib/api/users";
import { meetingsApi } from "@/lib/api/meetings";
import { navigationApi } from "@/lib/api/routes";
import type { CompanyOut, MeetingDetail, User } from "@/types";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Modal";
import { ScheduleMeetingModal } from "@/components/meetings/ScheduleMeetingModal";
import { Avatar } from "@/components/ui/Avatar";
import { Tabs } from "@/components/ui/Tabs";
import { LocationStatus } from "@/components/companies/LocationStatus";
import { ResolveLocationModal } from "@/components/companies/ResolveLocationModal";
import { Card, CardBody } from "@/components/ui/Card";
import { MeetingTimeline } from "@/components/meetings/MeetingTimeline";
import { useToast } from "@/components/ui/Toast";
import { LoadingSkeleton } from "@/components/ui/Spinner";

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [company, setCompany] = useState<CompanyOut | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [meetings, setMeetings] = useState<MeetingDetail[]>([]);
  const [scheduling, setScheduling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [resolvingLocation, setResolvingLocation] = useState(false);
  const [tab, setTab] = useState("overview");

  function load() {
    companiesApi.get(id).then(setCompany);
  }

  useEffect(load, [id]);
  useEffect(() => {
    usersApi.list().then((u) => setUsers(u.filter((x) => x.role === "salesperson")));
  }, []);
  useEffect(() => {
    meetingsApi.list().then((all) => setMeetings(all.filter((m) => m.company_id === id)));
  }, [id]);

  async function handleDelete() {
    if (!company) return;
    try {
      await companiesApi.remove(id);
      toast({ title: "Company deleted", description: company.name, variant: "success" });
      router.push("/admin/companies");
    } catch (err) {
      toast({
        title: "Couldn't delete company",
        description: err instanceof Error ? err.message : undefined,
        variant: "error",
      });
      setDeleting(false);
    }
  }

  async function handleNavigate() {
    const loc = company?.locations[0];
    if (!loc?.latitude || !loc?.longitude) return;
    try {
      const { url } = await navigationApi.getLink(loc.latitude, loc.longitude);
      const win = window.open(url, "_blank");
      if (!win) toast({ title: "Couldn't open navigation", description: "Check your popup blocker.", variant: "error" });
    } catch {
      toast({ title: "Couldn't open navigation", variant: "error" });
    }
  }

  const location = company?.locations[0] ?? null;

  const tabs = useMemo(
    () => [
      { key: "overview", label: "Overview" },
      { key: "contacts", label: "Contacts", count: company?.contacts.length ?? 0 },
      { key: "meetings", label: "Meetings", count: meetings.length },
    ],
    [company, meetings]
  );

  if (!company) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        <LoadingSkeleton className="h-8 w-64" />
        <LoadingSkeleton className="h-40 w-full" />
        <LoadingSkeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <Avatar name={company.name} size="lg" className="bg-navy-800 text-teal-300" />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-navy-900">{company.name}</h1>
              <Badge tone={statusTone(company.status)}>{company.status.replace("_", " ")}</Badge>
            </div>
            <p className="text-sm text-navy-500">{company.industry || "Industry unknown"}</p>
          </div>
        </div>
        <div className="flex gap-2">
          {location?.latitude && location?.longitude && (
            <Button variant="secondary" onClick={handleNavigate}>
              <NavigationIcon className="h-4 w-4" />
              Navigate
            </Button>
          )}
          <Button variant="secondary" onClick={() => setScheduling(true)}>
            <Calendar className="h-4 w-4" />
            Schedule
          </Button>
          <Button variant="danger" onClick={() => setDeleting(true)}>
            Delete
          </Button>
        </div>
      </div>

      <Tabs tabs={tabs} active={tab} onChange={setTab} className="mb-5" />

      {tab === "overview" && (
        <div className="space-y-5">
          <Section title="Location">
            <LocationStatus
              location={location}
              onNavigate={handleNavigate}
              onResolve={() => setResolvingLocation(true)}
            />
          </Section>
          <Section title="Company information">
            <dl className="space-y-1 text-sm">
              <Row label="Phone" value={company.phone} icon={<Phone className="h-3.5 w-3.5" />} />
              <Row label="Website" value={company.website} />
              <Row label="Employees" value={company.employee_count?.toString()} />
              <Row label="Parent company" value={company.parent_company} icon={<Building2 className="h-3.5 w-3.5" />} />
            </dl>
          </Section>
          {company.notes && (
            <Section title="Notes">
              <p className="text-sm text-navy-600">{company.notes}</p>
            </Section>
          )}
        </div>
      )}

      {tab === "contacts" && (
        <Section title={null}>
          {company.contacts.length === 0 ? (
            <p className="text-sm text-navy-500">No contacts imported.</p>
          ) : (
            <div className="space-y-2">
              {company.contacts.map((c) => (
                <div key={c.id} className="rounded-lg border border-navy-100 p-3 text-sm">
                  <p className="font-medium text-navy-800">{c.full_name || "Unnamed contact"}</p>
                  <p className="text-navy-500">
                    {c.title}
                    {c.email && ` · ${c.email}`}
                    {c.phone && ` · ${c.phone}`}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {tab === "meetings" && (
        <Section title={null}>
          <MeetingTimeline meetings={meetings} hrefFor={() => "/admin/meetings"} />
        </Section>
      )}

      <ScheduleMeetingModal
        open={scheduling}
        onClose={() => setScheduling(false)}
        company={company}
        salespeople={users}
        onScheduled={() => setScheduling(false)}
      />
      <ConfirmDialog
        open={deleting}
        title="Delete company"
        description={`Are you sure you want to delete ${company.name}? This cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleting(false)}
      />
      <ResolveLocationModal
        open={resolvingLocation}
        onClose={() => setResolvingLocation(false)}
        companyId={id}
        onResolved={load}
      />
    </div>
  );
}

function Section({ title, children }: { title: string | null; children: React.ReactNode }) {
  return (
    <Card>
      {title && (
        <div className="border-b border-navy-100 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-navy-800">{title}</h2>
        </div>
      )}
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function Row({ label, value, icon }: { label: string; value?: string | null; icon?: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-navy-50 py-1.5 last:border-0">
      <dt className="flex items-center gap-1.5 text-navy-500">
        {icon}
        {label}
      </dt>
      <dd className="text-navy-800">{value || "—"}</dd>
    </div>
  );
}
