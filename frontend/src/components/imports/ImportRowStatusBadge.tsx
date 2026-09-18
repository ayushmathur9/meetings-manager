import { Badge } from "@/components/ui/Badge";
import type { ImportRowOut } from "@/types";

const TONE: Record<ImportRowOut["status"], "success" | "warning" | "danger" | "info"> = {
  valid: "success",
  imported: "success",
  duplicate: "warning",
  error: "danger",
};

const LABEL: Record<ImportRowOut["status"], string> = {
  valid: "Valid",
  imported: "Imported",
  duplicate: "Duplicate",
  error: "Error",
};

export function ImportRowStatusBadge({ row }: { row: ImportRowOut }) {
  return (
    <div>
      <Badge tone={TONE[row.status]}>{LABEL[row.status]}</Badge>
      {row.status === "error" && row.error_reason && (
        <p className="mt-1 text-xs text-navy-400">{row.error_reason}</p>
      )}
    </div>
  );
}
