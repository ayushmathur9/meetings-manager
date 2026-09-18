"use client";

import { useEffect, useState } from "react";
import { Calendar } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { meetingsApi } from "@/lib/api/meetings";
import type { MeetingDetail } from "@/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { MeetingTimeline } from "@/components/meetings/MeetingTimeline";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";

export default function SalesMeetingsPage() {
  const { user } = useAuth();
  const [meetings, setMeetings] = useState<MeetingDetail[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    meetingsApi
      .list({ salesperson_id: user.id })
      .then(setMeetings)
      .finally(() => setLoading(false));
  }, [user]);

  return (
    <div className="p-6">
      <PageHeader title="My meetings" description="Upcoming and past meetings" />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : meetings.length === 0 ? (
        <EmptyState icon={<Calendar className="h-5 w-5" />} title="No meetings yet" />
      ) : (
        <MeetingTimeline meetings={meetings} variant="field" hrefFor={(m) => `/sales/meetings/${m.id}`} />
      )}
    </div>
  );
}
