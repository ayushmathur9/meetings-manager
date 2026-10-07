"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Building2, Calendar, MapPin, User as UserIcon } from "lucide-react";
import { meetingsApi } from "@/lib/api/meetings";
import type { MeetingDetail } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { BusinessOverview } from "@/components/companies/BusinessOverview";
import { MeetingRecorder } from "@/components/meetings/MeetingRecorder";

export default function AdminMeetingPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    meetingsApi.get(id).then(setMeeting).catch((err) => setError(err instanceof Error ? err.message : "Meeting not found"));
  }, [id]);

  if (!meeting) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-6">
        {error ? <p className="text-sm text-danger">{error}</p> : <LoadingSkeleton className="h-40 w-full" />}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 p-6">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1.5 text-sm font-medium text-navy-500 hover:text-navy-800"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <Card>
        <CardBody>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h1 className="text-xl font-semibold text-navy-900">{meeting.company_name}</h1>
            <Badge tone="info">{meeting.status.replace("_", " ")}</Badge>
          </div>
          <dl className="space-y-1.5 text-sm text-navy-600">
            <p className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-navy-400" />
              {meeting.date} · {meeting.start_time.slice(0, 5)}–{meeting.end_time.slice(0, 5)}
            </p>
            <p className="flex items-center gap-2">
              <UserIcon className="h-4 w-4 text-navy-400" />
              {meeting.salesperson_name}
              {meeting.contact_name && ` with ${meeting.contact_name}`}
            </p>
            <p className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-navy-400" />
              {[meeting.address_line_1, meeting.city, meeting.state].filter(Boolean).join(", ") || "Address pending verification"}
            </p>
            <p className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-navy-400" />
              <Link href={`/admin/companies/${meeting.company_id}`} className="text-teal-700 hover:underline">
                View company
              </Link>
            </p>
          </dl>
          {meeting.notes && <p className="mt-4 whitespace-pre-wrap border-t border-navy-50 pt-3 text-sm text-navy-700">{meeting.notes}</p>}
        </CardBody>
      </Card>

      <MeetingRecorder meetingId={meeting.id} disabled={meeting.status === "cancelled" || meeting.status === "no_show"} />
      <BusinessOverview companyId={meeting.company_id} />
    </div>
  );
}
