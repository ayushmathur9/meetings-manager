import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ImportStep {
  key: string;
  label: string;
}

export function ImportStepper({ steps, current }: { steps: ImportStep[]; current: string }) {
  const currentIndex = steps.findIndex((s) => s.key === current);

  return (
    <div className="mb-6 flex items-center">
      {steps.map((s, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        return (
          <div key={s.key} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
                  done && "bg-teal-500 text-white",
                  active && !done && "bg-navy-900 text-white",
                  !active && !done && "bg-navy-100 text-navy-400"
                )}
              >
                {done ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </div>
              <span className={cn("text-sm font-medium", active ? "text-navy-900" : "text-navy-400")}>
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className={cn("mx-3 h-px flex-1", done ? "bg-teal-400" : "bg-navy-100")} />
            )}
          </div>
        );
      })}
    </div>
  );
}
