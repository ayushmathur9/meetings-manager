"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Upload } from "lucide-react";
import { importsApi } from "@/lib/api/imports";
import type { ImportOut } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { PageHeader } from "@/components/layout/PageHeader";

export default function ImportsPage() {
  const [imports, setImports] = useState<ImportOut[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    importsApi.list().then((data) => {
      setImports(data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="p-6">
      <PageHeader
        title="Imports"
        description="Upload Excel or CSV prospect lists"
        actions={
          <Link href="/admin/imports/new">
            <Button>
              <Upload className="h-4 w-4" />
              New import
            </Button>
          </Link>
        }
      />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : imports.length === 0 ? (
        <EmptyState
          icon={<Upload className="h-5 w-5" />}
          title="No imports yet"
          description="Upload your first Excel or CSV file to bring prospects into Meetings Manager."
          action={
            <Link href="/admin/imports/new">
              <Button>New import</Button>
            </Link>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-navy-100 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
              <tr>
                <th className="px-4 py-3">File</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Imported</th>
                <th className="px-4 py-3">Duplicates</th>
                <th className="px-4 py-3">Errors</th>
                <th className="px-4 py-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {imports.map((i) => (
                <tr key={i.id} className="border-t border-navy-100 transition-colors hover:bg-navy-50/60">
                  <td className="px-4 py-3 font-medium text-navy-900">{i.filename}</td>
                  <td className="px-4 py-3">
                    <Badge tone={i.status === "completed" ? "success" : "neutral"}>{i.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-navy-700">{i.success_count}</td>
                  <td className="px-4 py-3 text-navy-700">{i.duplicate_count}</td>
                  <td className="px-4 py-3 text-navy-700">{i.error_count}</td>
                  <td className="px-4 py-3 text-navy-500">{new Date(i.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
