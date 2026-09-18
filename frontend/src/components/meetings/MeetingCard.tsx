import Link from "next/link";
import { Clock, MapPin, User as UserIcon } from "lucide-react";
import type { MeetingDetail } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

function meetingStatusTone(status: MeetingDetail["status"]) {
  switch (status) {
    case "completed":
      return "success" as const;
    case "in_progress":
      return "info" as const;
    case "cancelled":
    case "no_show":
      return "danger" as const;
    case "confirmed":
      return "info" as const;
    default:
      return "neutral" as const;
  }
}

export function MeetingCard({
  meeting,
  onOpen,
  variant = "admin",
  href,
}: {
  meeting: MeetingDetail;
  onOpen?: (meeting: MeetingDetail) => void;
  variant?: "admin" | "field" | "compact";
  href?: string;
}) {
  const body = (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border border-navy-100 bg-white px-4 py-3 transition-colors hover:border-navy-200 hover:bg-navy-50/40",
        variant === "compact" && "px-3 py-2.5"
      )}
    >
      <div className="w-14 shrink-0 text-sm font-semibold text-navy-800">
        {meeting.start_time.slice(0, 5)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-navy-900">{meeting.company_name}</p>
        <div className="mt-0.5 flex items-center gap-3 text-xs text-navy-500">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {meeting.duration_minutes} min
          </span>
          {variant !== "compact" && meeting.city && (
            <span className="flex items-center gap-1 truncate">
              <MapPin className="h-3 w-3 shrink-0" />
              {meeting.city}
              {meeting.state ? `, ${meeting.state}` : ""}
            </span>
          )}
          {variant === "admin" && (
            <span className="flex items-center gap-1 truncate">
              <UserIcon className="h-3 w-3 shrink-0" />
              {meeting.salesperson_name}
            </span>
          )}
        </div>
      </div>
      <Badge tone={meetingStatusTone(meeting.status)} className="shrink-0">
        {meeting.status.replace("_", " ")}
      </Badge>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block">
        {body}
      </Link>
    );
  }

  if (onOpen) {
    return (
      <button onClick={() => onOpen(meeting)} className="block w-full text-left">
        {body}
      </button>
    );
  }

  return body;
}
