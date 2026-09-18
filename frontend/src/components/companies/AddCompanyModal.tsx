"use client";

import { FormEvent, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { companiesApi } from "@/lib/api/companies";
import { useToast } from "@/components/ui/Toast";

export function AddCompanyModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: "",
    industry: "",
    phone: "",
    website: "",
    address_line_1: "",
    city: "",
    state: "",
    postal_code: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(field: string, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await companiesApi.create(form);
      toast({ title: "Company added", description: form.name, variant: "success" });
      setForm({
        name: "",
        industry: "",
        phone: "",
        website: "",
        address_line_1: "",
        city: "",
        state: "",
        postal_code: "",
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create company");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add company">
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormSection label="Company">
          <Field label="Company name" value={form.name} onChange={(v) => update("name", v)} required />
          <div className="flex gap-3">
            <Field label="Industry" value={form.industry} onChange={(v) => update("industry", v)} />
            <Field label="Phone" value={form.phone} onChange={(v) => update("phone", v)} />
          </div>
          <Field label="Website" value={form.website} onChange={(v) => update("website", v)} />
        </FormSection>
        <FormSection label="Location">
          <Field label="Address" value={form.address_line_1} onChange={(v) => update("address_line_1", v)} />
          <div className="flex gap-3">
            <Field label="City" value={form.city} onChange={(v) => update("city", v)} />
            <Field label="State" value={form.state} onChange={(v) => update("state", v)} />
            <Field label="ZIP" value={form.postal_code} onChange={(v) => update("postal_code", v)} />
          </div>
        </FormSection>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-navy-100 pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Adding..." : "Add company"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function FormSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-navy-400">{label}</p>
      {children}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <div className="flex-1">
      <label className="mb-1 block text-xs font-medium text-navy-600">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
      />
    </div>
  );
}
