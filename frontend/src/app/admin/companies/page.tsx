"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Plus, Search } from "lucide-react";
import { companiesApi } from "@/lib/api/companies";
import type { CompanyListItem } from "@/types";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { AddCompanyModal } from "@/components/companies/AddCompanyModal";
import { PageHeader } from "@/components/layout/PageHeader";

export default function CompaniesPage() {
  const [items, setItems] = useState<CompanyListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await companiesApi.list({ search: search || undefined, page_size: 100 });
      setItems(page.items);
      setTotal(page.total);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-6">
      <PageHeader
        title="Companies"
        description={`${total} companies`}
        actions={
          <>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search companies..."
                className="rounded-lg border border-navy-200 py-2 pl-8 pr-3 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
              />
            </div>
            <Button onClick={() => setAdding(true)}>
              <Plus className="h-4 w-4" />
              Add company
            </Button>
          </>
        }
      />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-5 w-5" />}
          title="No companies yet"
          description="Import your existing prospect list or add a company manually."
          action={<Button onClick={() => setAdding(true)}>Add company</Button>}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-navy-100 bg-white shadow-card">
          <table className="w-full text-sm">
            <thead className="bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
              <tr>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Industry</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Added</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-t border-navy-100 transition-colors hover:bg-navy-50/60">
                  <td className="px-4 py-3">
                    <Link href={`/admin/companies/${c.id}`} className="font-medium text-navy-900 hover:text-teal-700">
                      {c.name}
                    </Link>
                    {c.is_demo && (
                      <Badge tone="neutral" className="ml-2">
                        Demo
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-navy-600">{c.industry || "—"}</td>
                  <td className="px-4 py-3 text-navy-600">{c.phone || "—"}</td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(c.status)}>{c.status.replace("_", " ")}</Badge>
                  </td>
                  <td className="px-4 py-3 text-navy-500">{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddCompanyModal open={adding} onClose={() => setAdding(false)} onCreated={load} />
    </div>
  );
}
