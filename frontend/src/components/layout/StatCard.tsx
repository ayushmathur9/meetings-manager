import Link from "next/link";
import { cn } from "@/lib/utils";

type StatTone = "neutral" | "warning" | "danger" | "success";

const toneClasses: Record<StatTone, { value: string; icon: string; iconBg: string }> = {
  neutral: { value: "text-navy-900", icon: "text-navy-500", iconBg: "bg-navy-50" },
  warning: { value: "text-navy-900", icon: "text-warning", iconBg: "bg-amber-50" },
  danger: { value: "text-navy-900", icon: "text-danger", iconBg: "bg-red-50" },
  success: { value: "text-navy-900", icon: "text-success", iconBg: "bg-green-50" },
};

export function StatCard({
  label,
  value,
  icon,
  tone = "neutral",
  href,
  context,
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  tone?: StatTone;
  href?: string;
  context?: string;
}) {
  const style = toneClasses[tone];

  const content = (
    <div className="rounded-xl border border-navy-100 bg-white p-4 shadow-card transition-shadow hover:shadow-dropdown">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-navy-400">{label}</p>
          <p className={cn("mt-1.5 text-2xl font-semibold tabular-nums", style.value)}>{value}</p>
          {context && <p className="mt-1 truncate text-xs text-navy-500">{context}</p>}
        </div>
        {icon && (
          <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", style.iconBg, style.icon)}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block">
        {content}
      </Link>
    );
  }
  return content;
}
