"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Contact as ContactIcon,
  Info,
  MapPin,
  RefreshCw,
  ScrollText,
  XCircle,
} from "lucide-react";
import { crmSyncApi } from "@/lib/api/integrations";
import type { CrmSyncStatus, SyncRun, SyncRunDetail } from "@/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatCard } from "@/components/layout/StatCard";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { LoadingSkeleton, Spinner } from "@/components/ui/Spinner";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime, formatRelative } from "@/lib/format";

const TRIGGER_LABEL: Record<SyncRun["trigger"], string> = { manual: "Manual", scheduled: "Scheduled", webhook: "Bigin update" };
const STATUS_TONE = { running: "info", success: "success", partial: "warning", failed: "danger" } as const;

export default function CrmSyncPage() {
  const toast = useToast();
  const [status, setStatus] = useState<CrmSyncStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);

  const load = useCallback(() => {
    crmSyncApi
      .status()
      .then((s) => {
        setStatus(s);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Couldn't load sync status"));
  }, []);

  useEffect(load, [load]);

  // Refresh while a sync is running.
  useEffect(() => {
    if (!status?.running) return;
    const t = setTimeout(load, 3000);
    return () => clearTimeout(t);
  }, [status, load]);

  async function syncNow(full = false) {
    setStarting(true);
    try {
      await crmSyncApi.run(full);
      toast({ title: full ? "Full sync started" : "Sync started", variant: "info" });
      load();
    } catch (err) {
      toast({ title: "Couldn't start sync", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setStarting(false);
    }
  }

  if (!status) {
    return (
      <div className="p-6">
        <PageHeader title="CRM Sync" description="Companies and contacts from Zoho Bigin" />
        {loadError ? <p className="text-sm text-danger">{loadError}</p> : <LoadingSkeleton className="h-40 w-full" />}
      </div>
    );
  }

  const { connection, counts } = status;
  const running = !!status.running;

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="CRM Sync"
        description="Companies and contacts are synchronized from Zoho Bigin, the source of truth for CRM data."
        actions={
          <>
            <Button variant="secondary" onClick={() => setLogsOpen(true)}>
              <ScrollText className="h-4 w-4" /> View Sync Logs
            </Button>
            <Button onClick={() => syncNow(false)} disabled={!connection.configured || running || starting}>
              {running || starting ? <Spinner className="h-4 w-4 text-white" /> : <RefreshCw className="h-4 w-4" />}
              {running ? "Syncing..." : "Sync Now"}
            </Button>
          </>
        }
      />

      <Card className="mb-5">
        <CardBody className="flex flex-wrap items-start justify-between gap-4">
          <ConnectionBadge status={status} />
          <dl className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-3">
            <Meta label="Last successful sync" value={status.last_success_at ? formatDateTime(status.last_success_at) : "Never"} />
            <Meta
              label="Next sync"
              value={running ? "In progress" : status.next_sync_at ? `${formatRelative(status.next_sync_at)}` : "—"}
              hint={status.interval_minutes > 0 ? `Every ${status.interval_minutes} min` : "Scheduled sync off"}
            />
            <Meta
              label="Instant updates"
              value={status.webhooks.active ? "Active" : status.webhooks.enabled ? "Not active" : "Off"}
              hint={
                status.webhooks.active
                  ? status.webhooks.last_notification_at
                    ? `Last event ${formatRelative(status.webhooks.last_notification_at)}`
                    : "Waiting for changes"
                  : status.webhooks.error || (status.webhooks.enabled ? undefined : "Needs PUBLIC_API_BASE_URL")
              }
            />
          </dl>
        </CardBody>
        {status.last_error && (
          <div className="flex items-start gap-2 border-t border-navy-100 bg-red-50/50 px-5 py-3 text-sm text-danger">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            Last sync failed: {status.last_error}
          </div>
        )}
      </Card>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Companies" value={counts.companies} icon={<Building2 className="h-4 w-4" />} href="/admin/companies"
          context={counts.archived ? `${counts.archived} archived (deleted in Bigin)` : undefined} />
        <StatCard label="Contacts" value={counts.contacts} icon={<ContactIcon className="h-4 w-4" />} />
        <StatCard label="Locations" value={counts.locations} icon={<MapPin className="h-4 w-4" />} tone="success" context="Verified on the map" />
        <StatCard label="Needs review" value={counts.needs_review} icon={<AlertTriangle className="h-4 w-4" />}
          tone={counts.needs_review ? "warning" : "neutral"} href="/admin/prospects" context="Address couldn't be confirmed" />
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-navy-800">Recent activity</h2>
          {connection.configured && (
            <button className="text-xs font-medium text-navy-500 hover:text-navy-800 disabled:opacity-50"
              onClick={() => syncNow(true)} disabled={running || starting} title="Re-read every record from Bigin">
              Run full resync
            </button>
          )}
        </CardHeader>
        <CardBody>
          {status.recent_runs.length === 0 ? (
            <p className="text-sm text-navy-500">
              {connection.configured ? "No syncs yet — click Sync Now to import from Bigin." : "Connect Bigin to start syncing."}
            </p>
          ) : (
            <ul className="space-y-3">
              {status.recent_runs.map((run) => (
                <li key={run.id} className="flex items-start gap-3 text-sm">
                  <RunIcon run={run} />
                  <div className="min-w-0 flex-1">
                    <p className="text-navy-800">{activityLines(run).join(" · ") || runHeadline(run)}</p>
                    <p className="text-xs text-navy-500">
                      {TRIGGER_LABEL[run.trigger]}
                      {run.full && " full sync"} · {formatDateTime(run.started_at)}
                      {run.triggered_by_name && ` · ${run.triggered_by_name}`}
                    </p>
                    {run.locations_needs_review > 0 && (
                      <p className="mt-0.5 text-xs text-warning">
                        ⚠ {run.locations_needs_review} location{run.locations_needs_review === 1 ? "" : "s"} need review
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <SyncLogsModal open={logsOpen} onClose={() => setLogsOpen(false)} />
    </div>
  );
}

function ConnectionBadge({ status }: { status: CrmSyncStatus }) {
  const { connection } = status;
  let icon = <Info className="h-5 w-5 text-navy-400" />;
  let title = "Not configured";
  let detail = "Set BIGIN_CLIENT_ID, BIGIN_CLIENT_SECRET and BIGIN_REFRESH_TOKEN on the backend service.";
  if (connection.configured && connection.ok) {
    icon = <CheckCircle2 className="h-5 w-5 text-success" />;
    title = "Connected";
    detail = connection.checked_at ? `Verified ${formatRelative(connection.checked_at)}` : "";
  } else if (connection.configured) {
    icon = <XCircle className="h-5 w-5 text-danger" />;
    title = "Connection failed";
    detail = connection.error || "Bigin could not be reached.";
  }
  return (
    <div className="flex items-start gap-3">
      {icon}
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-navy-400">Zoho Bigin</p>
        <p className="text-base font-semibold text-navy-900">{title}</p>
        {detail && <p className="max-w-md text-xs text-navy-500">{detail}</p>}
      </div>
    </div>
  );
}

function Meta({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-xs text-navy-500">{label}</dt>
      <dd className="font-medium text-navy-800">{value}</dd>
      {hint && <dd className="text-xs text-navy-400">{hint}</dd>}
    </div>
  );
}

function RunIcon({ run }: { run: SyncRun }) {
  if (run.status === "running") return <Spinner className="mt-0.5 h-4 w-4 shrink-0" />;
  if (run.status === "failed") return <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />;
  if (run.status === "partial") return <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />;
  return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />;
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function activityLines(run: SyncRun): string[] {
  const lines: string[] = [];
  if (run.companies_created) lines.push(`${plural(run.companies_created, "company", "companies")} added`);
  if (run.companies_updated) lines.push(`${plural(run.companies_updated, "company", "companies")} updated`);
  if (run.contacts_created) lines.push(`${plural(run.contacts_created, "contact", "contacts")} added`);
  if (run.contacts_updated) lines.push(`${plural(run.contacts_updated, "contact", "contacts")} updated`);
  if (run.addresses_changed) lines.push(`${plural(run.addresses_changed, "address", "addresses")} changed`);
  if (run.records_deleted) lines.push(`${plural(run.records_deleted, "record", "records")} archived`);
  return lines;
}

function runHeadline(run: SyncRun): string {
  if (run.status === "running") return "Sync in progress...";
  if (run.status === "failed") return run.message || "Sync failed";
  return "No changes";
}

function SyncLogsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [runs, setRuns] = useState<SyncRun[] | null>(null);
  const [selected, setSelected] = useState<SyncRunDetail | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    crmSyncApi.runs().then(setRuns).catch(() => setRuns([]));
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title={selected ? "Sync details" : "Sync logs"} className="max-w-2xl">
      {selected ? (
        <div className="space-y-4 text-sm">
          <button className="text-xs font-medium text-teal-700 hover:underline" onClick={() => setSelected(null)}>
            ← All runs
          </button>
          <div className="flex items-center gap-2">
            <Badge tone={STATUS_TONE[selected.status]}>{selected.status}</Badge>
            <span className="text-navy-600">
              {TRIGGER_LABEL[selected.trigger]}{selected.full && " full sync"} · {formatDateTime(selected.started_at)}
            </span>
          </div>
          {selected.message && <p className="text-navy-700">{selected.message}</p>}
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {([
              ["Companies added", selected.companies_created], ["Companies updated", selected.companies_updated],
              ["Contacts added", selected.contacts_created], ["Contacts updated", selected.contacts_updated],
              ["Addresses changed", selected.addresses_changed], ["Locations verified", selected.locations_verified],
              ["Needs review", selected.locations_needs_review], ["Archived", selected.records_deleted],
              ["Skipped", selected.records_skipped],
            ] as [string, number][]).map(([label, n]) => (
              <div key={label} className="rounded-lg bg-navy-50 px-3 py-2">
                <dt className="text-xs text-navy-500">{label}</dt>
                <dd className="font-semibold tabular-nums text-navy-900">{n}</dd>
              </div>
            ))}
          </dl>
          {selected.errors && selected.errors.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-navy-500">Records that failed</h3>
              <ul className="max-h-60 space-y-1 overflow-y-auto text-xs">
                {selected.errors.map((e, i) => (
                  <li key={i} className="rounded border border-navy-100 px-2 py-1">
                    <span className="font-mono text-navy-500">{e.module} {e.bigin_id ?? "?"}</span>: {e.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : runs === null ? (
        <LoadingSkeleton className="h-40 w-full" />
      ) : runs.length === 0 ? (
        <p className="text-sm text-navy-500">No sync has run yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-navy-400">
              <th className="pb-2 font-medium">Started</th>
              <th className="pb-2 font-medium">Trigger</th>
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2 font-medium">Changes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-navy-50">
            {runs.map((run) => (
              <tr key={run.id} className="cursor-pointer hover:bg-navy-50"
                onClick={() => crmSyncApi.run_detail(run.id).then(setSelected)}>
                <td className="py-2 pr-2 text-navy-700">{formatDateTime(run.started_at)}</td>
                <td className="py-2 pr-2 text-navy-600">{TRIGGER_LABEL[run.trigger]}{run.full && " (full)"}</td>
                <td className="py-2 pr-2"><Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge></td>
                <td className="py-2 text-xs text-navy-600">{activityLines(run).join(", ") || runHeadline(run)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-4 text-xs text-navy-400">
        Companies needing review can be fixed from <Link href="/admin/prospects" className="text-teal-700 hover:underline">Prospects</Link>.
      </p>
    </Modal>
  );
}
