"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navigation as NavigationIcon, MapPin } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { meetingsApi } from "@/lib/api/meetings";
import { routesApi, navigationApi } from "@/lib/api/routes";
import type { MeetingDetail, RouteOut } from "@/types";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/layout/PageHeader";
import { useToast } from "@/components/ui/Toast";

export default function SalesDashboard() {
  const { user } = useAuth();
  const toast = useToast();
  const [meetings, setMeetings] = useState<MeetingDetail[]>([]);
  const [route, setRoute] = useState<RouteOut | null>(null);
  const today = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    if (!user) return;
    meetingsApi.list({ salesperson_id: user.id, date_from: today, date_to: today }).then(setMeetings);
    routesApi.getByDate(user.id, today).then(setRoute);
  }, [user, today]);

  const nextMeeting = meetings.find((m) => m.status === "scheduled" || m.status === "confirmed");

  async function handleNavigate(lat: number | null, lng: number | null) {
    if (!lat || !lng) return;
    try {
      const { url } = await navigationApi.getLink(lat, lng);
      const win = window.open(url, "_blank");
      if (!win) toast({ title: "Couldn't open navigation", description: "Check your popup blocker.", variant: "error" });
    } catch {
      toast({ title: "Couldn't open navigation", variant: "error" });
    }
  }

  return (
    <div className="p-6">
      <PageHeader
        title={`Hi ${user?.name.split(" ")[0] ?? ""}`}
        description="Here's your day at a glance."
      />

      {nextMeeting ? (
        <Card className="mb-6 border-teal-200 bg-teal-50/60">
          <CardBody>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-teal-700">Next meeting</p>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-xl font-semibold text-navy-900">{nextMeeting.company_name}</p>
                <p className="mt-0.5 text-sm text-navy-600">
                  {nextMeeting.start_time.slice(0, 5)} · {nextMeeting.address_line_1 || "Address pending"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button size="lg" onClick={() => handleNavigate(nextMeeting.latitude, nextMeeting.longitude)}>
                  <NavigationIcon className="h-4 w-4" />
                  Navigate
                </Button>
                <Link href={`/sales/meetings/${nextMeeting.id}`}>
                  <Button size="lg" variant="secondary">
                    Open
                  </Button>
                </Link>
              </div>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div className="mb-6">
          <EmptyState
            icon={<MapPin className="h-5 w-5" />}
            title="No meetings scheduled for today"
            description="Your schedule is clear."
          />
        </div>
      )}

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-navy-800">Today&apos;s route</h2>
        </CardHeader>
        <CardBody>
          {!route || route.stops.length === 0 ? (
            <EmptyState title="No route created yet" description="Ask your admin to generate today's route." />
          ) : (
            <ol className="space-y-2">
              {route.stops.map((stop) => (
                <li key={stop.id} className="flex items-center justify-between border-b border-navy-50 py-2.5 text-sm last:border-0">
                  <div className="min-w-0">
                    <span className="mr-2 font-semibold text-teal-700">{stop.sequence}.</span>
                    <span className="font-medium text-navy-800">{stop.company_name}</span>
                    <span className="ml-2 text-navy-500">{stop.arrival_time?.slice(0, 5)}</span>
                  </div>
                  <Badge tone="info">{stop.meeting_status.replace("_", " ")}</Badge>
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
