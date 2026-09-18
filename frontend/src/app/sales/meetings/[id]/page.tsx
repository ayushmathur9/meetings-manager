"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Globe, Navigation as NavigationIcon, Phone } from "lucide-react";
import { meetingsApi } from "@/lib/api/meetings";
import { navigationApi } from "@/lib/api/routes";
import type { MeetingDetail } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";

export default function FieldMeetingPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [notes, setNotes] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    meetingsApi.get(id).then((m) => {
      setMeeting(m);
      setNotes(m.notes || "");
    });
  }

  useEffect(load, [id]);

  async function handleNavigate() {
    if (!meeting?.latitude || !meeting?.longitude) return;
    try {
      const { url } = await navigationApi.getLink(meeting.latitude, meeting.longitude);
      const win = window.open(url, "_blank");
      if (!win) toast({ title: "Couldn't open navigation", description: "Check your popup blocker.", variant: "error" });
    } catch {
      toast({ title: "Couldn't open navigation", variant: "error" });
    }
  }

  const statusMessages: Record<string, string> = {
    in_progress: "Meeting started",
    completed: "Meeting completed",
    cancelled: "Meeting cancelled",
    no_show: "Marked as no-show",
  };

  async function updateStatus(status: string) {
    setSaving(true);
    try {
      await meetingsApi.update(id, {
        status,
        notes,
        next_follow_up_date: followUpDate || undefined,
      });
      toast({ title: statusMessages[status] ?? "Meeting updated", variant: "success" });
      load();
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveNotes() {
    setSaving(true);
    try {
      await meetingsApi.update(id, { notes });
      toast({ title: "Notes saved", variant: "success" });
    } finally {
      setSaving(false);
    }
  }

  if (!meeting) {
    return (
      <div className="mx-auto max-w-lg space-y-4 p-6">
        <LoadingSkeleton className="h-6 w-24" />
        <LoadingSkeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg p-6 pb-28">
      <button
        onClick={() => router.back()}
        className="mb-4 flex items-center gap-1.5 text-sm font-medium text-navy-500 hover:text-navy-800"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <div className="rounded-xl border border-navy-100 bg-white p-6 shadow-card">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-navy-900">{meeting.company_name}</h1>
          <Badge tone="info">{meeting.status.replace("_", " ")}</Badge>
        </div>

        <div className="mb-5 space-y-1 text-sm text-navy-600">
          {meeting.contact_name && <p>Contact: {meeting.contact_name}</p>}
          <p>
            {meeting.date} · {meeting.start_time.slice(0, 5)}–{meeting.end_time.slice(0, 5)}
          </p>
          <p>{meeting.address_line_1 || "Address pending verification"}</p>
          {meeting.company_phone && <p>{meeting.company_phone}</p>}
        </div>

        <div className="mb-6 grid grid-cols-3 gap-2">
          <Button size="lg" className="flex-col gap-1" onClick={handleNavigate} disabled={!meeting.latitude || !meeting.longitude}>
            <NavigationIcon className="h-4 w-4" />
            Navigate
          </Button>
          {meeting.company_phone ? (
            <a href={`tel:${meeting.company_phone}`}>
              <Button size="lg" variant="secondary" className="w-full flex-col gap-1">
                <Phone className="h-4 w-4" />
                Call
              </Button>
            </a>
          ) : (
            <Button size="lg" variant="secondary" className="flex-col gap-1" disabled>
              <Phone className="h-4 w-4" />
              Call
            </Button>
          )}
          {meeting.company_website ? (
            <a href={meeting.company_website} target="_blank" rel="noreferrer">
              <Button size="lg" variant="secondary" className="w-full flex-col gap-1">
                <Globe className="h-4 w-4" />
                Website
              </Button>
            </a>
          ) : (
            <Button size="lg" variant="secondary" className="flex-col gap-1" disabled>
              <Globe className="h-4 w-4" />
              Website
            </Button>
          )}
        </div>

        {meeting.status === "scheduled" || meeting.status === "confirmed" ? (
          <Button size="lg" className="w-full" onClick={() => updateStatus("in_progress")} disabled={saving}>
            Start meeting
          </Button>
        ) : meeting.status === "in_progress" ? (
          <div className="space-y-3">
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-center text-sm font-medium text-warning">
              Meeting in progress
            </p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Meeting notes..."
              rows={4}
              className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
            />
            <div>
              <label className="mb-1 block text-xs font-medium text-navy-600">Next follow-up date</label>
              <input
                type="date"
                value={followUpDate}
                onChange={(e) => setFollowUpDate(e.target.value)}
                className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
              />
            </div>
            <Button size="lg" className="w-full" onClick={() => updateStatus("completed")} disabled={saving}>
              Complete meeting
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
            />
            <Button size="lg" variant="secondary" className="w-full" onClick={handleSaveNotes} disabled={saving}>
              Save notes
            </Button>
          </div>
        )}

        {(meeting.status === "scheduled" || meeting.status === "confirmed") && (
          <div className="mt-4 flex justify-center gap-4 text-xs">
            <button className="text-navy-500 hover:text-navy-800" onClick={() => updateStatus("cancelled")}>
              Cancel meeting
            </button>
            <button className="text-navy-500 hover:text-navy-800" onClick={() => updateStatus("no_show")}>
              Mark no-show
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
