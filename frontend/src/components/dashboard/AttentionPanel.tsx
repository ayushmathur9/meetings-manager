import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/Card";

export interface AttentionItem {
  icon: React.ReactNode;
  title: string;
  description: string;
  count: number;
  actionLabel: string;
  href: string;
}

export function AttentionPanel({ items }: { items: AttentionItem[] }) {
  const active = items.filter((i) => i.count > 0);

  if (active.length === 0) {
    return (
      <Card className="px-5 py-8 text-center">
        <p className="text-sm font-medium text-navy-700">All caught up</p>
        <p className="mt-1 text-sm text-navy-500">Nothing needs your attention right now.</p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="divide-y divide-navy-100">
        {active.map((item, i) => (
          <Link
            key={i}
            href={item.href}
            className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-navy-50/60"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-warning">
              {item.icon}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-navy-900">
                {item.count} {item.title}
              </p>
              <p className="truncate text-xs text-navy-500">{item.description}</p>
            </div>
            <span className="flex shrink-0 items-center gap-1 text-sm font-medium text-teal-600">
              {item.actionLabel}
              <ChevronRight className="h-3.5 w-3.5" />
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}
