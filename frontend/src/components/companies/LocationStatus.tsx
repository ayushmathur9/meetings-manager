import { CheckCircle2, HelpCircle, MapPin, Navigation as NavigationIcon, XCircle } from "lucide-react";
import type { LocationOut } from "@/types";
import { cn } from "@/lib/utils";

const SOURCE_LABELS: Record<string, string> = {
  user_provided: "Manually entered",
  geocoded: "Geocoded",
  verified_business: "Verified business listing",
  needs_verification: "Imported, unverified",
};

function statusMeta(status: LocationOut["verification_status"]) {
  switch (status) {
    case "verified":
      return { label: "Verified", icon: CheckCircle2, color: "text-success", bg: "bg-green-50" };
    case "needs_review":
      return { label: "Needs Review", icon: HelpCircle, color: "text-warning", bg: "bg-amber-50" };
    case "failed":
      return { label: "Verification Failed", icon: XCircle, color: "text-danger", bg: "bg-red-50" };
    default:
      return { label: "Unverified", icon: HelpCircle, color: "text-navy-500", bg: "bg-navy-100" };
  }
}

export function LocationStatus({
  location,
  onNavigate,
  onResolve,
  compact = false,
}: {
  location: LocationOut | null;
  onNavigate?: () => void;
  onResolve?: () => void;
  compact?: boolean;
}) {
  if (!location) {
    return (
      <div className="flex items-center gap-2 text-sm text-navy-500">
        <MapPin className="h-4 w-4 shrink-0" />
        No location on file
      </div>
    );
  }

  const meta = statusMeta(location.verification_status);
  const Icon = meta.icon;
  const address = [location.address_line_1, location.address_line_2].filter(Boolean).join(", ");
  const cityLine = [location.city, location.state, location.postal_code].filter(Boolean).join(", ");

  if (compact) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", meta.color)}>
        <Icon className="h-3.5 w-3.5" />
        {meta.label}
      </span>
    );
  }

  return (
    <div className="rounded-lg border border-navy-100 p-3">
      <div className={cn("mb-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold", meta.bg, meta.color)}>
        <Icon className="h-3.5 w-3.5" />
        {meta.label}
      </div>
      <p className="text-sm text-navy-800">{address || "Address needs verification"}</p>
      {cityLine && <p className="text-sm text-navy-500">{cityLine}</p>}

      <div className="mt-3 flex items-center gap-4 text-xs text-navy-500">
        <span>
          Source: <span className="font-medium text-navy-700">{SOURCE_LABELS[location.source] ?? location.source}</span>
        </span>
        {location.confidence && (
          <span>
            Confidence: <span className="font-medium text-navy-700 capitalize">{location.confidence}</span>
          </span>
        )}
      </div>

      {location.verification_notes && (
        <p className="mt-2 text-xs text-warning">{location.verification_notes}</p>
      )}

      {location.latitude && location.longitude ? (
        onNavigate && (
          <button
            onClick={onNavigate}
            className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-teal-600 hover:text-teal-700"
          >
            <NavigationIcon className="h-3.5 w-3.5" />
            Navigate
          </button>
        )
      ) : (
        <div className="mt-3 flex items-center justify-between gap-2">
          <p className="text-xs text-warning">Coordinates not yet verified</p>
          {onResolve && (
            <button
              onClick={onResolve}
              className="shrink-0 text-sm font-medium text-teal-600 hover:text-teal-700"
            >
              Review candidates
            </button>
          )}
        </div>
      )}
    </div>
  );
}
