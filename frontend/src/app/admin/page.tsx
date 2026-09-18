"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Calendar, MapPinOff, Users } from "lucide-react";
import { prospectsApi } from "@/lib/api/prospects";
import { meetingsApi } from "@/lib/api/meetings";
import type { MeetingDetail, ProspectListItem } from "@/types";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/layout/StatCard";
import { AttentionPanel } from "@/components/dashboard/AttentionPanel";
import { TodaysWork } from "@/components/dashboard/TodaysWork";
import { ProspectMap, type MapMarkerPoint } from "@/components/map/ProspectMap";

export default function AdminDashboard() {
  const [prospects, setProspects] = useState<ProspectListItem[]>([]);
  const [todayMeetings, setTodayMeetings] = useState<MeetingDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const today = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    Promise.all([
      prospectsApi.list({ page_size: 500 }).then((p) => setProspects(p.items)),
      meetingsApi.list({ date_from: today, date_to: today }).then(setTodayMeetings),
    ]).finally(() => setLoading(false));
  }, [today]);

  const unassigned = prospects.filter((p) => !p.assigned_user_id).length;
  const needsVerification = prospects.filter(
    (p) => p.verification_status && p.verification_status !== "verified"
  ).length;
  const upcoming = todayMeetings.filter((m) => m.status === "scheduled" || m.status === "confirmed").length;
  const completedToday = todayMeetings.filter((m) => m.status === "completed").length;
  const nextMeeting = [...todayMeetings]
    .filter((m) => m.status === "scheduled" || m.status === "confirmed")
    .sort((a, b) => a.start_time.localeCompare(b.start_time))[0];

  const markers = useMemo<MapMarkerPoint[]>(
    () =>
      todayMeetings
        .filter((m) => m.latitude && m.longitude)
        .map((m) => ({
          id: m.id,
          lat: m.latitude!,
          lng: m.longitude!,
          label: m.company_name,
          status: m.status === "completed" ? "completed" : "scheduled",
        })),
    [todayMeetings]
  );

  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  }, []);

  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="p-6">
      <PageHeader
        title={`${greeting}, team`}
        description={`${dateLabel} · Here's what needs your attention today.`}
      />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Total prospects" value={loading ? "—" : prospects.length} icon={<Users className="h-4 w-4" />} />
        <StatCard
          label="Meetings today"
          value={loading ? "—" : todayMeetings.length}
          context={loading ? undefined : `${completedToday} completed`}
          icon={<Calendar className="h-4 w-4" />}
        />
        <StatCard
          label="Upcoming"
          value={loading ? "—" : upcoming}
          context={nextMeeting ? `Next: ${nextMeeting.start_time.slice(0, 5)}` : undefined}
          icon={<Calendar className="h-4 w-4" />}
        />
        <StatCard
          label="Unassigned"
          value={loading ? "—" : unassigned}
          tone={unassigned > 0 ? "warning" : "neutral"}
          context={unassigned > 0 ? "Needs attention" : undefined}
          icon={<Users className="h-4 w-4" />}
        />
        <StatCard
          label="Location issues"
          value={loading ? "—" : needsVerification}
          tone={needsVerification > 0 ? "danger" : "neutral"}
          context={needsVerification > 0 ? "Review required" : undefined}
          icon={<MapPinOff className="h-4 w-4" />}
        />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card className="h-[440px] overflow-hidden p-2">
          <ProspectMap markers={markers} />
        </Card>
        <Card className="flex h-[440px] flex-col">
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Today&apos;s work</h2>
          </CardHeader>
          <CardBody className="scrollbar-thin flex-1 overflow-y-auto">
            <TodaysWork meetings={todayMeetings} />
          </CardBody>
        </Card>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-navy-800">Attention required</h2>
        <AttentionPanel
          items={[
            {
              icon: <AlertTriangle className="h-4 w-4" />,
              title: "companies need location review",
              description: "Verify addresses to keep routing accurate",
              count: needsVerification,
              actionLabel: "Review",
              href: "/admin/prospects?verification_status=needs_review",
            },
            {
              icon: <Users className="h-4 w-4" />,
              title: "prospects need an owner",
              description: "Assign a salesperson to move these forward",
              count: unassigned,
              actionLabel: "Assign",
              href: "/admin/prospects?unassigned_only=true",
            },
          ]}
        />
      </div>
    </div>
  );
}
