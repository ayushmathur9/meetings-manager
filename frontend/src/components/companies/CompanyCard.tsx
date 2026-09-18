import { Building2, MapPin, User as UserIcon } from "lucide-react";
import type { ProspectListItem } from "@/types";
import { Badge, statusTone, verificationTone } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

export function CompanyCard({
  item,
  selected,
  onSelect,
  onOpen,
  reduced = false,
}: {
  item: ProspectListItem;
  selected?: boolean;
  onSelect?: (id: string) => void;
  onOpen: (id: string) => void;
  reduced?: boolean;
}) {
  const distanceMiles = item.distance_meters != null ? (item.distance_meters / 1609.34).toFixed(1) : null;

  return (
    <div
      onClick={() => onOpen(item.company_id)}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border border-navy-100 bg-white p-4 transition-colors hover:border-navy-200 hover:bg-navy-50/40",
        selected && "border-teal-300 bg-teal-50/50 ring-1 ring-teal-300"
      )}
    >
      {onSelect && (
        <input
          type="checkbox"
          checked={!!selected}
          onChange={() => onSelect(item.company_id)}
          onClick={(e) => e.stopPropagation()}
          className="mt-1 shrink-0"
        />
      )}
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-navy-100 text-navy-500">
        <Building2 className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="truncate text-sm font-semibold text-navy-900">{item.company_name}</p>
          <Badge tone={statusTone(item.status)}>{item.status.replace("_", " ")}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-navy-500">{item.industry || "Uncategorized"}</p>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-navy-500">
          {item.city && (
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {item.city}, {item.state}
              {distanceMiles && <span className="text-navy-400"> · {distanceMiles} mi</span>}
            </span>
          )}
          <Badge tone={verificationTone(item.verification_status)} className="!py-0.5">
            {item.verification_status ? item.verification_status.replace("_", " ") : "no location"}
          </Badge>
          {!reduced && (
            <span className="flex items-center gap-1">
              <UserIcon className="h-3 w-3" />
              {item.assigned_user_name || "Unassigned"}
            </span>
          )}
          {item.has_contact && <span>{item.contact_count} contact{item.contact_count === 1 ? "" : "s"}</span>}
        </div>
      </div>
    </div>
  );
}
