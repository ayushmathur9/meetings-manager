"use client";

import { AppShell } from "@/components/AppShell";

export default function SalesLayout({ children }: { children: React.ReactNode }) {
  return <AppShell role="salesperson">{children}</AppShell>;
}
