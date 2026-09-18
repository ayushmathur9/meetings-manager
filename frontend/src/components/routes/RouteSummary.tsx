"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Play } from "lucide-react";
import type { RouteOut } from "@/types";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

function formatMinutes(totalSeconds: number) {
  const minutes = Math.round(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours === 0) return `${mins} min`;
  return `${hours} hr${mins ? ` ${mins} min` : ""}`;
}

export function RouteSummary({ route }: { route: RouteOut }) {
  const router = useRouter();
  const { user } = useAuth();
  const toast = useToast();
  const [highlight, setHighlight] = useState(false);

  const meetingSeconds = route.stops.reduce((sum, s) => {
    if (!s.arrival_time || !s.departure_time) return sum;
    const [ah, am] = s.arrival_time.split(":").map(Number);
    const [dh, dm] = s.departure_time.split(":").map(Number);
    return sum + (dh * 3600 + dm * 60 - (ah * 3600 + am * 60));
  }, 0);

  const drivingSeconds =
    route.estimated_duration_seconds ?? route.stops.reduce((sum, s) => sum + (s.travel_time_seconds ?? 0), 0);

  const totalSeconds = meetingSeconds + drivingSeconds;
  const firstStop = route.stops[0];

  function handleStart() {
    if (!firstStop) return;

    if (user?.role !== "admin") {
      router.push(`/sales/meetings/${firstStop.meeting_id}`);
      return;
    }

    const timeline = document.getElementById("route-timeline");
    timeline?.scrollIntoView({ behavior: "smooth", block: "start" });
    setHighlight(true);
    setTimeout(() => setHighlight(false), 1500);
    toast({
      title: "Route ready",
      description: "Review the stops below, or open the salesperson's meetings to track progress.",
      variant: "info",
    });
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-white px-5 py-4 shadow-card transition-shadow",
        highlight ? "border-teal-400 ring-2 ring-teal-300" : "border-navy-100"
      )}
    >
      <div className="flex flex-wrap gap-6 text-sm">
        <Stat label="Meetings" value={String(route.stops.length)} />
        <Stat label="Meeting time" value={formatMinutes(meetingSeconds)} />
        <Stat label="Driving time" value={formatMinutes(drivingSeconds)} />
        <Stat label="Total" value={formatMinutes(totalSeconds)} emphasized />
      </div>
      <Button disabled={!firstStop} onClick={handleStart}>
        <Play className="h-4 w-4" />
        Start Route
      </Button>
    </div>
  );
}

function Stat({ label, value, emphasized }: { label: string; value: string; emphasized?: boolean }) {
  return (
    <div>
      <p className="text-xs text-navy-400">{label}</p>
      <p className={emphasized ? "text-base font-semibold text-navy-900" : "text-sm font-medium text-navy-700"}>
        {value}
      </p>
    </div>
  );
}
