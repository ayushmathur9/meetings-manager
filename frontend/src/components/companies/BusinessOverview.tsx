"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { researchApi } from "@/lib/api/integrations";
import type { CompanyResearch, ResearchSource } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const IN_PROGRESS = ["pending", "researching", "summarizing"];
const PROGRESS_LABEL: Record<string, string> = {
  pending: "Queued...",
  researching: "Researching public sources...",
  summarizing: "Writing summary...",
};
const SOURCE_TYPE_LABEL: Record<ResearchSource["source_type"], string> = {
  website: "Website",
  crm: "CRM record",
  location: "Verified address",
};

/**
 * Pre-meeting business overview: an AI summary built only from gathered
 * sources (company website, CRM record, verified address). Every statement
 * cites its sources; nothing is shown as fact without one.
 */
export function BusinessOverview({ companyId, compact = false }: { companyId: string; compact?: boolean }) {
  const toast = useToast();
  const [research, setResearch] = useState<CompanyResearch | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showSources, setShowSources] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(() => {
    researchApi
      .get(companyId)
      .then((r) => {
        setResearch(r);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load the business overview"));
  }, [companyId]);

  useEffect(() => {
    setResearch(null);
    load();
  }, [load]);

  // Poll while research runs in the background.
  useEffect(() => {
    if (research?.status && IN_PROGRESS.includes(research.status)) {
      timer.current = setTimeout(load, 3000);
    }
    return () => clearTimeout(timer.current);
  }, [research, load]);

  async function handleRefresh() {
    try {
      setResearch(await researchApi.refresh(companyId));
    } catch (err) {
      toast({ title: "Couldn't refresh summary", description: err instanceof Error ? err.message : undefined, variant: "error" });
    }
  }

  const busy = !!research?.status && IN_PROGRESS.includes(research.status);
  const data = research?.summary_data ?? null;
  const sourcesByRef = new Map((research?.sources ?? []).map((s) => [s.ref, s]));
  const hasSummary = !!research?.summary;

  return (
    <div className={cn(compact ? "" : "rounded-xl border border-navy-100 bg-white shadow-card")}>
      <div className={cn("flex items-center justify-between gap-3", compact ? "mb-2" : "border-b border-navy-100 px-5 py-3.5")}>
        <h2 className={cn("flex items-center gap-2", compact ? "text-xs font-semibold uppercase tracking-wide text-navy-500" : "text-sm font-semibold text-navy-800")}>
          {!compact && <Sparkles className="h-4 w-4 text-teal-500" />}
          Business Overview
        </h2>
        <Button variant="ghost" size="sm" onClick={handleRefresh} disabled={busy || !research} title="Re-research and regenerate">
          <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
          {compact ? "" : "Refresh Summary"}
        </Button>
      </div>

      <div className={cn(compact ? "" : "px-5 py-4", "space-y-4 text-sm")}>
        {loadError && <p className="text-danger">{loadError}</p>}

        {!research && !loadError && (
          <div className="flex items-center gap-2 text-navy-500">
            <Spinner className="h-4 w-4" /> Loading...
          </div>
        )}

        {busy && (
          <div className="flex items-center gap-2 rounded-lg bg-teal-50 px-3 py-2 text-teal-700">
            <Spinner className="h-4 w-4 text-teal-600" />
            {PROGRESS_LABEL[research!.status!]}
            {hasSummary && <span className="text-teal-600/80">— showing the previous summary meanwhile</span>}
          </div>
        )}

        {research?.status === null && (
          <div className="text-navy-500">
            No overview yet.{" "}
            <button className="font-medium text-teal-700 hover:underline" onClick={handleRefresh}>
              Generate one
            </button>
          </div>
        )}

        {research?.status === "failed" && research.error && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-warning">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{research.error}</span>
          </div>
        )}

        {hasSummary && data && (
          <>
            <div>
              <p className="leading-relaxed text-navy-800">
                {research!.summary} <Refs refs={data.what_they_do?.source_refs} sources={sourcesByRef} />
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {data.industry && <Badge tone="info">{data.industry.text}</Badge>}
                {data.confidence !== "high" && (
                  <Badge tone="warning">{data.confidence === "low" ? "Limited public info" : "Partly verified"}</Badge>
                )}
              </div>
            </div>

            {data.footprint.length > 0 && (
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-navy-500">Footprint</h3>
                <ul className="space-y-1 text-navy-700">
                  {data.footprint.map((f, i) => (
                    <li key={i}>
                      {f.text} <Refs refs={f.source_refs} sources={sourcesByRef} />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-navy-500">Why this may matter</h3>
              {data.it_relevance.length > 0 ? (
                <ul className="space-y-1.5">
                  {data.it_relevance.map((r, i) => (
                    <li key={i} className="text-navy-700">
                      <span className="font-medium text-navy-800">{r.signal}</span>
                      {r.why_it_matters && <> — {r.why_it_matters}</>} <Refs refs={r.source_refs} sources={sourcesByRef} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-navy-500">No IT-relevant signals were stated in the sources.</p>
              )}
            </div>
          </>
        )}

        {research?.status === "completed" && !hasSummary && data && (
          <p className="text-navy-500">
            Not enough reliable public information to write an overview.
            {data.caveats && <span className="block pt-1 text-navy-400">{data.caveats}</span>}
          </p>
        )}

        {hasSummary && data?.caveats && <p className="text-xs text-navy-400">{data.caveats}</p>}

        {research && research.sources.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-navy-50 pt-3 text-xs text-navy-500">
            <button className="font-medium text-teal-700 hover:underline" onClick={() => setShowSources((v) => !v)}>
              {showSources ? "Hide sources" : `View sources (${research.sources.length})`}
            </button>
            <span>
              {research.generated_at ? `Last updated ${formatDateTime(research.generated_at)}` : "Not generated yet"}
              {research.is_stale && " · out of date"}
            </span>
          </div>
        )}

        {showSources && research && (
          <ul className="space-y-1.5 text-xs">
            {research.sources.map((s) => (
              <li key={s.ref} className="flex items-start gap-2">
                <span className="mt-px rounded bg-navy-100 px-1.5 py-0.5 font-mono text-[10px] text-navy-600">{s.ref}</span>
                <span className="min-w-0">
                  <span className="text-navy-500">{SOURCE_TYPE_LABEL[s.source_type]}: </span>
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noopener noreferrer" className="break-all text-teal-700 hover:underline">
                      {s.title || s.url}
                      <ExternalLink className="ml-1 inline h-3 w-3" />
                    </a>
                  ) : (
                    <span className="text-navy-700">{s.title}</span>
                  )}
                </span>
              </li>
            ))}
            {research.model && <li className="pt-1 text-navy-400">Summarized by AI ({research.model}) from the sources above.</li>}
          </ul>
        )}
      </div>
    </div>
  );
}

function Refs({ refs, sources }: { refs?: string[]; sources: Map<string, ResearchSource> }) {
  if (!refs?.length) return null;
  return (
    <span className="whitespace-nowrap">
      {refs.map((ref) => {
        const s = sources.get(ref);
        return (
          <sup key={ref} className="ml-0.5 text-[10px] font-medium text-teal-700" title={s ? `${SOURCE_TYPE_LABEL[s.source_type]}: ${s.title || s.url || ""}` : ref}>
            [{ref}]
          </sup>
        );
      })}
    </span>
  );
}
