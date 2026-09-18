"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { CommandSearch } from "@/components/ui/CommandSearch";
import { ADMIN_NAV, SALES_NAV } from "@/components/layout/nav";

export function AppShell({
  role,
  children,
}: {
  role: "admin" | "salesperson";
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const nav = role === "admin" ? ADMIN_NAV : SALES_NAV;
  const [commandOpen, setCommandOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    } else if (!loading && user && user.role !== role) {
      router.replace(user.role === "admin" ? "/admin" : "/sales");
    }
  }, [loading, user, role, router]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  if (loading || !user || user.role !== role) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy-50 text-navy-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-navy-50">
      <Sidebar
        groups={nav}
        user={user}
        onLogout={async () => {
          await logout();
          router.push("/login");
        }}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar user={user} onOpenCommandSearch={() => setCommandOpen(true)} />
        <main className="scrollbar-thin flex-1 overflow-y-auto">{children}</main>
      </div>
      <CommandSearch open={commandOpen} onClose={() => setCommandOpen(false)} />
    </div>
  );
}
