import { Calendar } from "lucide-react";
import type { MeetingDetail } from "@/types";
import { MeetingCard } from "@/components/meetings/MeetingCard";
import { EmptyState } from "@/components/ui/EmptyState";

export function TodaysWork({
  meetings,
  onSelect,
  selectedId,
}: {
  meetings: MeetingDetail[];
  onSelect?: (meeting: MeetingDetail) => void;
  selectedId?: string;
}) {
  const sorted = [...meetings].sort((a, b) => a.start_time.localeCompare(b.start_time));

  if (sorted.length === 0) {
    return (
      <EmptyState
        icon={<Calendar className="h-5 w-5" />}
        title="No meetings scheduled"
        description="Your schedule is clear for today."
      />
    );
  }

  return (
    <div className="space-y-2">
      {sorted.map((m) => (
        <div
          key={m.id}
          onClick={() => onSelect?.(m)}
          className={
            onSelect
              ? "cursor-pointer rounded-lg " + (selectedId === m.id ? "ring-2 ring-teal-400" : "")
              : ""
          }
        >
          <MeetingCard meeting={m} variant="compact" />
        </div>
      ))}
    </div>
  );
}
