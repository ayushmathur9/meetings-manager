"use client";

import { useEffect, useMemo, useState } from "react";
import { Calendar } from "lucide-react";
import { meetingsApi } from "@/lib/api/meetings";
import type { MeetingDetail } from "@/types";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { MeetingTimeline } from "@/components/meetings/MeetingTimeline";
import { EmptyState } from "@/components/ui/EmptyState";

function startOfWeek(d: Date) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  date.setDate(diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

export default function AdminMeetingsPage() {
  const [meetings, setMeetings] = useState<MeetingDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("today");

  useEffect(() => {
    meetingsApi.list().then((data) => {
      setMeetings(data);
      setLoading(false);
    });
  }, []);

  const { todayList, weekList, upcomingList } = useMemo(() => {
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);
    const weekStart = startOfWeek(now);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);

    return {
      todayList: meetings.filter((m) => m.date === todayStr),
      weekList: meetings.filter((m) => {
        const d = new Date(m.date);
        return d >= weekStart && d <= weekEnd;
      }),
      upcomingList: meetings.filter((m) => m.date >= todayStr && (m.status === "scheduled" || m.status === "confirmed")),
    };
  }, [meetings]);

  const lists: Record<string, MeetingDetail[]> = {
    today: todayList,
    week: weekList,
    upcoming: upcomingList,
  };

  return (
    <div className="p-6">
      <PageHeader title="Meetings" description="All scheduled and completed meetings" />

      <Tabs
        tabs={[
          { key: "today", label: "Today", count: todayList.length },
          { key: "week", label: "This Week", count: weekList.length },
          { key: "upcoming", label: "Upcoming", count: upcomingList.length },
        ]}
        active={tab}
        onChange={setTab}
        className="mb-5"
      />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : lists[tab].length === 0 ? (
        <EmptyState
          icon={<Calendar className="h-5 w-5" />}
          title="No meetings here"
          description="Schedule a meeting from a company's prospect profile."
        />
      ) : (
        <MeetingTimeline meetings={lists[tab]} hrefFor={(m) => `/admin/companies/${m.company_id}`} />
      )}
    </div>
  );
}
