import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-navy-100 text-navy-600",
  success: "bg-green-50 text-success",
  warning: "bg-amber-50 text-warning",
  danger: "bg-red-50 text-danger",
  info: "bg-teal-50 text-teal-700",
};

const dotClasses: Record<BadgeTone, string> = {
  neutral: "bg-navy-400",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-teal-500",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium leading-none",
        toneClasses[tone],
        className
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotClasses[tone])} />
      {children}
    </span>
  );
}

export function statusTone(status: string): BadgeTone {
  switch (status) {
    case "new":
      return "info";
    case "meeting":
    case "follow_up":
      return "warning";
    case "not_interested":
    case "not_a_fit":
      return "danger";
    case "existing_customer":
      return "success";
    default:
      return "neutral";
  }
}

export function verificationTone(status: string | null): BadgeTone {
  if (status === "verified") return "success";
  if (status === "needs_review" || status === "unverified") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}
