import { cn } from "@/lib/utils";
import type { MapMarkerPoint } from "./ProspectMap";

const STATUS_COLORS: Record<MapMarkerPoint["status"], string> = {
  unassigned: "#5b80a8",
  assigned: "#26a69c",
  scheduled: "#b8720b",
  completed: "#1a9e5c",
  needs_verification: "#c0362c",
};

export function CompanyMarker({
  status,
  selected,
  count,
}: {
  status: MapMarkerPoint["status"];
  selected?: boolean;
  count?: number;
}) {
  if (count && count > 1) {
    return (
      <div
        className={cn(
          "flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-2 border-white text-xs font-semibold text-white shadow-md transition-transform",
          selected && "scale-125"
        )}
        style={{ backgroundColor: "#213a56" }}
      >
        {count}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "cursor-pointer rounded-full border-2 border-white shadow-md transition-transform",
        selected ? "h-6 w-6 ring-2 ring-teal-400 ring-offset-1" : "h-5 w-5"
      )}
      style={{ backgroundColor: STATUS_COLORS[status] }}
    />
  );
}
