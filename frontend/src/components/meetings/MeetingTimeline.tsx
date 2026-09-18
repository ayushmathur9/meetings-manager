import { useMemo } from "react";
import { MeetingCard } from "./MeetingCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Calendar } from "lucide-react";
import type { MeetingDetail } from "@/types";

export function MeetingTimeline({
  meetings,
  onOpen,
  hrefFor,
  variant = "admin",
}: {
  meetings: MeetingDetail[];
  onOpen?: (meeting: MeetingDetail) => void;
  hrefFor?: (meeting: MeetingDetail) => string;
  variant?: "admin" | "field";
}) {
  const sorted = useMemo(
    () =>
      [...meetings].sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time)),
    [meetings]
  );

  if (sorted.length === 0) {
    return (
      <EmptyState
        icon={<Calendar className="h-5 w-5" />}
        title="No meetings scheduled"
        description="Your schedule is clear."
      />
    );
  }

  return (
    <div className="space-y-2">
      {sorted.map((m) => (
        <MeetingCard
          key={m.id}
          meeting={m}
          variant={variant}
          onOpen={onOpen}
          href={hrefFor?.(m)}
        />
      ))}
    </div>
  );
}
