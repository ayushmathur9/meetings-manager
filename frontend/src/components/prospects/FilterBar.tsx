import { cn } from "@/lib/utils";

export function FilterBar({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-end gap-3 rounded-lg border border-navy-100 bg-white p-3", className)}>
      {children}
    </div>
  );
}

export function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-navy-500">{label}</label>
      {children}
    </div>
  );
}

export const filterInputClass =
  "rounded-lg border border-navy-200 px-3 py-1.5 text-sm text-navy-800 outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring";
