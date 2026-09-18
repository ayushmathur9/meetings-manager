"use client";

import { useEffect, useState } from "react";
import { MapPin } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { companiesApi } from "@/lib/api/companies";
import type { LocationCandidate } from "@/types";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

export function ResolveLocationModal({
  open,
  onClose,
  companyId,
  onResolved,
}: {
  open: boolean;
  onClose: () => void;
  companyId: string;
  onResolved: () => void;
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<LocationCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    companiesApi
      .getLocationCandidates(companyId)
      .then((res) => setCandidates(res.candidates))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to search for this address"))
      .finally(() => setLoading(false));
  }, [open, companyId]);

  async function handleApply() {
    if (selected === null) return;
    setApplying(true);
    try {
      await companiesApi.resolveLocation(companyId, candidates[selected]);
      toast({ title: "Location verified", description: candidates[selected].formatted_address, variant: "success" });
      onResolved();
      onClose();
    } catch (err) {
      toast({
        title: "Couldn't apply this location",
        description: err instanceof Error ? err.message : undefined,
        variant: "error",
      });
    } finally {
      setApplying(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Review location candidates" className="max-w-md">
      <p className="mb-4 text-sm text-navy-500">
        Pick the correct address for this company. We&apos;ll save it as verified.
      </p>

      {loading ? (
        <div className="space-y-2">
          <LoadingSkeleton className="h-16 w-full" />
          <LoadingSkeleton className="h-16 w-full" />
          <LoadingSkeleton className="h-16 w-full" />
        </div>
      ) : error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>
      ) : candidates.length === 0 ? (
        <EmptyState
          icon={<MapPin className="h-5 w-5" />}
          title="No matches found"
          description="We couldn't find any candidate addresses for this company. Try updating its address first."
        />
      ) : (
        <div className="scrollbar-thin max-h-80 space-y-2 overflow-y-auto">
          {candidates.map((c, i) => (
            <button
              key={i}
              onClick={() => setSelected(i)}
              className={cn(
                "w-full rounded-lg border p-3 text-left text-sm transition-colors",
                selected === i ? "border-teal-400 bg-teal-50/60 ring-1 ring-teal-300" : "border-navy-100 hover:bg-navy-50/60"
              )}
            >
              <p className="font-medium text-navy-800">{c.formatted_address}</p>
              <p className="mt-0.5 text-xs text-navy-400">Confidence: {c.confidence}</p>
            </button>
          ))}
        </div>
      )}

      <div className="mt-5 flex justify-end gap-2 border-t border-navy-100 pt-4">
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={handleApply} disabled={selected === null || applying}>
          {applying ? "Saving..." : "Use this address"}
        </Button>
      </div>
    </Modal>
  );
}
