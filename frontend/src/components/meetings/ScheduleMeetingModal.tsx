"use client";

import { FormEvent, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { meetingsApi } from "@/lib/api/meetings";
import type { CompanyOut, User } from "@/types";
import { useToast } from "@/components/ui/Toast";

const inputClass =
  "w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring";

export function ScheduleMeetingModal({
  open,
  onClose,
  company,
  salespeople,
  onScheduled,
  defaultSalespersonId,
}: {
  open: boolean;
  onClose: () => void;
  company: CompanyOut;
  salespeople: User[];
  onScheduled: () => void;
  defaultSalespersonId?: string;
}) {
  const toast = useToast();
  const [salespersonId, setSalespersonId] = useState(defaultSalespersonId || salespeople[0]?.id || "");
  const [contactId, setContactId] = useState(company.contacts[0]?.id || "");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [startTime, setStartTime] = useState("09:00");
  const [duration, setDuration] = useState(25);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await meetingsApi.create({
        company_id: company.id,
        contact_id: contactId || null,
        salesperson_id: salespersonId,
        date,
        start_time: `${startTime}:00`,
        duration_minutes: duration,
        notes: notes || undefined,
      });
      toast({ title: "Meeting scheduled", description: `${company.name} · ${date} at ${startTime}`, variant: "success" });
      onScheduled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to schedule meeting");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Schedule meeting — ${company.name}`}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-navy-600">Salesperson</label>
          <select value={salespersonId} onChange={(e) => setSalespersonId(e.target.value)} required className={inputClass}>
            {salespeople.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
        {company.contacts.length > 0 && (
          <div>
            <label className="mb-1 block text-xs font-medium text-navy-600">Contact</label>
            <select value={contactId} onChange={(e) => setContactId(e.target.value)} className={inputClass}>
              <option value="">No specific contact</option>
              {company.contacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-navy-600">Date</label>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required className={inputClass} />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-navy-600">Start time</label>
            <input
              type="time"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              required
              className={inputClass}
            />
          </div>
          <div className="w-28">
            <label className="mb-1 block text-xs font-medium text-navy-600">Duration (min)</label>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              min={5}
              step={5}
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-navy-600">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className={inputClass} />
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-navy-100 pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Scheduling..." : "Schedule meeting"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
