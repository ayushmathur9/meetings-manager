"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Calendar, CornerDownLeft, LayoutDashboard, Search } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { prospectsApi } from "@/lib/api/prospects";
import { meetingsApi } from "@/lib/api/meetings";
import type { MeetingDetail, ProspectListItem } from "@/types";
import { cn } from "@/lib/utils";

const CACHE_TTL_MS = 60_000;

let cache: { prospects: ProspectListItem[]; meetings: MeetingDetail[]; fetchedAt: number } | null = null;

interface NavCommand {
  type: "nav";
  key: string;
  label: string;
  href: string;
}

interface ProspectResult {
  type: "prospect";
  key: string;
  item: ProspectListItem;
}

interface MeetingResult {
  type: "meeting";
  key: string;
  item: MeetingDetail;
}

type ResultItem = NavCommand | ProspectResult | MeetingResult;

const ADMIN_COMMANDS: NavCommand[] = [
  { type: "nav", key: "nav-dashboard", label: "Go to Dashboard", href: "/admin" },
  { type: "nav", key: "nav-prospects", label: "Go to Prospects", href: "/admin/prospects" },
  { type: "nav", key: "nav-companies", label: "Go to Companies", href: "/admin/companies" },
  { type: "nav", key: "nav-meetings", label: "Go to Meetings", href: "/admin/meetings" },
  { type: "nav", key: "nav-routes", label: "Go to Routes", href: "/admin/routes" },
  { type: "nav", key: "nav-imports", label: "Go to Imports", href: "/admin/imports" },
  { type: "nav", key: "nav-team", label: "Go to Team", href: "/admin/team" },
];

const SALES_COMMANDS: NavCommand[] = [
  { type: "nav", key: "nav-dashboard", label: "Go to Dashboard", href: "/sales" },
  { type: "nav", key: "nav-prospects", label: "Go to My Prospects", href: "/sales/prospects" },
  { type: "nav", key: "nav-meetings", label: "Go to My Meetings", href: "/sales/meetings" },
  { type: "nav", key: "nav-route", label: "Go to My Route", href: "/sales/route" },
];

export function CommandSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [prospects, setProspects] = useState<ProspectListItem[]>([]);
  const [meetings, setMeetings] = useState<MeetingDetail[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    requestAnimationFrame(() => inputRef.current?.focus());

    const now = Date.now();
    if (cache && now - cache.fetchedAt < CACHE_TTL_MS) {
      setProspects(cache.prospects);
      setMeetings(cache.meetings);
      return;
    }

    Promise.all([
      prospectsApi.list({ page_size: 200 }).catch(() => ({ items: [] as ProspectListItem[] })),
      meetingsApi.list().catch(() => [] as MeetingDetail[]),
    ]).then(([prospectPage, meetingList]) => {
      cache = { prospects: prospectPage.items, meetings: meetingList, fetchedAt: Date.now() };
      setProspects(prospectPage.items);
      setMeetings(meetingList);
    });
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const navCommands = user?.role === "admin" ? ADMIN_COMMANDS : SALES_COMMANDS;

  const results = useMemo<ResultItem[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return navCommands.map((c) => c);
    }

    const matchedNav = navCommands.filter((c) => c.label.toLowerCase().includes(q));

    const matchedProspects: ProspectResult[] = prospects
      .filter(
        (p) =>
          p.company_name.toLowerCase().includes(q) ||
          (p.industry ?? "").toLowerCase().includes(q) ||
          (p.city ?? "").toLowerCase().includes(q)
      )
      .slice(0, 8)
      .map((item) => ({ type: "prospect", key: `p-${item.company_id}`, item }));

    const matchedMeetings: MeetingResult[] = meetings
      .filter(
        (m) =>
          m.company_name.toLowerCase().includes(q) ||
          (m.contact_name ?? "").toLowerCase().includes(q)
      )
      .slice(0, 8)
      .map((item) => ({ type: "meeting", key: `m-${item.id}`, item }));

    return [...matchedNav, ...matchedProspects, ...matchedMeetings];
  }, [query, navCommands, prospects, meetings]);

  useEffect(() => {
    setActiveIndex(0);
  }, [results.length, query]);

  function go(item: ResultItem) {
    if (item.type === "nav") {
      router.push(item.href);
    } else if (item.type === "prospect") {
      router.push(user?.role === "admin" ? "/admin/prospects" : "/sales/prospects");
    } else if (item.type === "meeting") {
      router.push(
        user?.role === "admin" ? "/admin/meetings" : `/sales/meetings/${item.item.id}`
      );
    }
    onClose();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = results[activeIndex];
      if (item) go(item);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-60 flex items-start justify-center bg-navy-950/40 px-4 pt-24 animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-xl bg-white shadow-2xl animate-slide-up"
      >
        <div className="flex items-center gap-2.5 border-b border-navy-100 px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-navy-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search companies, contacts, meetings..."
            className="flex-1 bg-transparent text-sm text-navy-900 outline-none placeholder:text-navy-400"
          />
          <kbd className="rounded border border-navy-200 px-1.5 py-0.5 text-[10px] font-medium text-navy-400">
            ESC
          </kbd>
        </div>
        <div className="scrollbar-thin max-h-80 overflow-y-auto p-2">
          {results.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-navy-400">No results found</p>
          )}
          {results.map((item, i) => (
            <button
              key={item.key}
              onClick={() => go(item)}
              onMouseEnter={() => setActiveIndex(i)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                i === activeIndex ? "bg-navy-50" : "hover:bg-navy-50/60"
              )}
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-navy-100 text-navy-500">
                {item.type === "nav" && <LayoutDashboard className="h-4 w-4" />}
                {item.type === "prospect" && <Building2 className="h-4 w-4" />}
                {item.type === "meeting" && <Calendar className="h-4 w-4" />}
              </span>
              <span className="min-w-0 flex-1">
                {item.type === "nav" && <span className="font-medium text-navy-800">{item.label}</span>}
                {item.type === "prospect" && (
                  <>
                    <span className="block truncate font-medium text-navy-800">{item.item.company_name}</span>
                    <span className="block truncate text-xs text-navy-400">
                      {item.item.industry || "Company"} {item.item.city ? `· ${item.item.city}` : ""}
                    </span>
                  </>
                )}
                {item.type === "meeting" && (
                  <>
                    <span className="block truncate font-medium text-navy-800">{item.item.company_name}</span>
                    <span className="block truncate text-xs text-navy-400">
                      {item.item.date} · {item.item.start_time.slice(0, 5)}
                      {item.item.contact_name ? ` · ${item.item.contact_name}` : ""}
                    </span>
                  </>
                )}
              </span>
              {i === activeIndex && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-navy-300" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
