"use client";

import { useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Activity as ActivityIcon } from "lucide-react";
import { api } from "@/lib/api/client";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { PageHeader } from "@/components/layout/PageHeader";

interface ActivityRow {
  id: string;
  user_name: string;
  entity_type: string;
  action: string;
  timestamp: string;
}

export default function ActivityPage() {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<ActivityRow[]>("/activity?limit=200")
      .then(setRows)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6">
      <PageHeader title="Activity log" description="Audit trail of key actions" />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<ActivityIcon className="h-5 w-5" />} title="No activity recorded yet" />
      ) : (
        <div className="overflow-hidden rounded-xl border border-navy-100 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Entity</th>
                <th className="px-4 py-3">Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-navy-100">
                  <td className="px-4 py-3 font-medium text-navy-800">{r.user_name}</td>
                  <td className="px-4 py-3 text-navy-600">{r.action}</td>
                  <td className="px-4 py-3 text-navy-500">{r.entity_type}</td>
                  <td className="px-4 py-3 text-navy-400" title={new Date(r.timestamp).toLocaleString()}>
                    {formatDistanceToNow(new Date(r.timestamp), { addSuffix: true })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
