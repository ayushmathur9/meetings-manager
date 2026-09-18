"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { prospectsApi } from "@/lib/api/prospects";
import { usersApi } from "@/lib/api/users";
import type { ProspectListItem, User } from "@/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { PageHeader } from "@/components/layout/PageHeader";
import { CompanyCard } from "@/components/companies/CompanyCard";
import { ProspectDrawer } from "@/components/prospects/ProspectDrawer";
import { Users } from "lucide-react";

export default function SalesProspectsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<ProspectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [salespeople, setSalespeople] = useState<User[]>([]);
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);

  const load = () => {
    if (!user) return;
    setLoading(true);
    prospectsApi
      .list({ assigned_user_id: user.id, page_size: 200 })
      .then((p) => setItems(p.items))
      .finally(() => setLoading(false));
  };

  useEffect(load, [user]);
  useEffect(() => {
    usersApi.list().then((u) => setSalespeople(u.filter((x) => x.role === "salesperson")));
  }, []);

  return (
    <div className="p-6">
      <PageHeader title="My prospects" description={`${items.length} companies assigned to you`} />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Users className="h-5 w-5" />}
          title="No prospects assigned yet"
          description="Your admin will assign prospects to you."
        />
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <CompanyCard key={p.company_id} item={p} onOpen={setActiveCompanyId} reduced />
          ))}
        </div>
      )}

      <ProspectDrawer
        companyId={activeCompanyId}
        assignedUserId={items.find((i) => i.company_id === activeCompanyId)?.assigned_user_id}
        onClose={() => setActiveCompanyId(null)}
        salespeople={salespeople}
        onChanged={load}
      />
    </div>
  );
}
