"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ExternalLink, LogOut, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar } from "@/components/ui/Avatar";
import { appConfigApi } from "@/lib/api/integrations";
import type { AppConfig, User } from "@/types";
import type { NavGroup, NavItem } from "./nav";

export function Sidebar({
  groups,
  user,
  onLogout,
}: {
  groups: NavGroup[];
  user: User;
  onLogout: () => void;
}) {
  const pathname = usePathname();
  const [config, setConfig] = useState<AppConfig | null>(null);

  useEffect(() => {
    appConfigApi.get().then(setConfig).catch(() => setConfig({ quote_builder_url: null }));
  }, []);

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-navy-950 text-white">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500 text-navy-950">
          <MapPin className="h-4 w-4" strokeWidth={2.5} />
        </div>
        <span className="text-sm font-semibold tracking-tight">Meetings Manager</span>
      </div>

      <nav className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {groups.map((group, gi) => (
          <div key={gi}>
            {group.label && (
              <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-wider text-navy-500">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                if (item.external) {
                  return <ExternalNavLink key={item.href} item={item} url={config ? config.quote_builder_url : undefined} />;
                }
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-white/10 text-white"
                        : "text-navy-400 hover:bg-white/5 hover:text-navy-100"
                    )}
                  >
                    <Icon
                      className={cn("h-4 w-4 shrink-0", active ? "text-teal-400" : "text-navy-500")}
                      strokeWidth={2}
                    />
                    <span className="truncate">{item.label}</span>
                    {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-teal-400" />}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-white/10 px-3 py-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
          <Avatar name={user.name} size="sm" className="bg-navy-800 text-teal-300" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{user.name}</p>
            <p className="truncate text-xs text-navy-500">{user.email}</p>
          </div>
          <button
            onClick={onLogout}
            className="shrink-0 rounded-md p-1.5 text-navy-500 transition-colors hover:bg-white/10 hover:text-teal-400"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}

/** A sidebar entry for an external tool: opens in a new tab, marked with an
 * external-link icon. Shown disabled (not hidden) when its URL isn't
 * configured, so it's clear the tool exists but needs setting up. */
function ExternalNavLink({ item, url }: { item: NavItem; url: string | null | undefined }) {
  const Icon = item.icon;
  const base = "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors";
  if (!url) {
    return (
      <span
        className={cn(base, "cursor-not-allowed text-navy-600")}
        title={url === undefined ? "Loading..." : `${item.label} isn't configured yet — ask an administrator to set QUOTE_BUILDER_URL.`}
        aria-disabled="true"
      >
        <Icon className="h-4 w-4 shrink-0 text-navy-700" strokeWidth={2} />
        <span className="truncate">{item.label}</span>
        {url === null && <span className="ml-auto text-[10px] uppercase tracking-wide text-navy-700">Not set</span>}
      </span>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${item.label} (external tool, new tab)`}
      className={cn(base, "text-navy-400 hover:bg-white/5 hover:text-navy-100")}
    >
      <Icon className="h-4 w-4 shrink-0 text-navy-500" strokeWidth={2} />
      <span className="truncate">{item.label}</span>
      <ExternalLink className="ml-auto h-3.5 w-3.5 shrink-0 text-navy-500" aria-label="Opens in a new tab" />
    </a>
  );
}
