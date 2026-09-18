"use client";

import { Bell, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { Avatar } from "@/components/ui/Avatar";
import type { User } from "@/types";

const TITLES: { match: (path: string) => boolean; title: string }[] = [
  { match: (p) => p === "/admin", title: "Dashboard" },
  { match: (p) => p === "/sales", title: "My Day" },
  { match: (p) => p === "/admin/prospects", title: "Prospects" },
  { match: (p) => p === "/sales/prospects", title: "My Prospects" },
  { match: (p) => p === "/admin/companies", title: "Companies" },
  { match: (p) => /^\/admin\/companies\/.+/.test(p), title: "Company" },
  { match: (p) => p === "/admin/meetings", title: "Meetings" },
  { match: (p) => p === "/sales/meetings", title: "My Meetings" },
  { match: (p) => /^\/sales\/meetings\/.+/.test(p), title: "Meeting" },
  { match: (p) => p === "/admin/routes", title: "Routes" },
  { match: (p) => p === "/sales/route", title: "My Route" },
  { match: (p) => p === "/admin/imports", title: "Imports" },
  { match: (p) => p === "/admin/imports/new", title: "New Import" },
  { match: (p) => p === "/admin/team", title: "Team" },
  { match: (p) => p === "/admin/activity", title: "Activity" },
  { match: (p) => p === "/admin/settings", title: "Settings" },
];

function titleFor(pathname: string) {
  return TITLES.find((t) => t.match(pathname))?.title ?? "Meetings Manager";
}

export function Topbar({
  user,
  onOpenCommandSearch,
}: {
  user: User;
  onOpenCommandSearch: () => void;
}) {
  const pathname = usePathname();
  const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-navy-100 bg-white px-6">
      <h1 className="truncate text-sm font-semibold text-navy-900">{titleFor(pathname)}</h1>

      <div className="flex flex-1 items-center justify-end gap-3">
        <button
          onClick={onOpenCommandSearch}
          className="flex w-full max-w-xs items-center gap-2 rounded-lg border border-navy-200 bg-navy-50/60 px-3 py-1.5 text-sm text-navy-400 transition-colors hover:border-navy-300 hover:bg-navy-50"
        >
          <Search className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate text-left">Search companies, meetings...</span>
          <kbd className="hidden shrink-0 rounded border border-navy-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-navy-400 sm:inline">
            {isMac ? "⌘K" : "Ctrl K"}
          </kbd>
        </button>

        <button
          className="shrink-0 rounded-lg p-2 text-navy-400 transition-colors hover:bg-navy-50 hover:text-navy-600"
          aria-label="Notifications"
          title="Notifications"
        >
          <Bell className="h-4 w-4" />
        </button>

        <div className="flex shrink-0 items-center gap-2 border-l border-navy-100 pl-3">
          <Avatar name={user.name} size="sm" />
          <div className="hidden leading-tight md:block">
            <p className="text-xs font-medium text-navy-800">{user.name}</p>
            <p className="text-[11px] capitalize text-navy-400">{user.role}</p>
          </div>
        </div>
      </div>
    </header>
  );
}
