"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, HelpCircle, Upload, XCircle } from "lucide-react";
import { importsApi } from "@/lib/api/imports";
import { MAPPABLE_FIELD_LABELS } from "@/lib/import-fields";
import type { ImportLocationSummary, ImportPreview, ValidationSummary } from "@/types";
import { Button } from "@/components/ui/Button";
import { StatCard } from "@/components/layout/StatCard";
import { ImportStepper } from "@/components/imports/ImportStepper";
import { ImportRowStatusBadge } from "@/components/imports/ImportRowStatusBadge";
import { PageHeader } from "@/components/layout/PageHeader";
import { useToast } from "@/components/ui/Toast";

type Step = "upload" | "map" | "validate" | "done";

const STEPS = [
  { key: "upload", label: "Upload" },
  { key: "map", label: "Map Columns" },
  { key: "validate", label: "Review" },
  { key: "done", label: "Import" },
];

export default function NewImportPage() {
  const router = useRouter();
  const toast = useToast();
  const [step, setStep] = useState<Step>("upload");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [locationSummary, setLocationSummary] = useState<ImportLocationSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const result = await importsApi.upload(file);
      setPreview(result);
      const initialMapping: Record<string, string> = {};
      Object.entries(result.suggested_mapping).forEach(([field, column]) => {
        if (column) initialMapping[field] = column;
      });
      setMapping(initialMapping);
      setStep("map");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleValidate() {
    if (!preview) return;
    setUploading(true);
    setError(null);
    try {
      const result = await importsApi.applyMapping(preview.import_id, mapping);
      setValidation(result);
      setStep("validate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm() {
    if (!preview || !validation) return;
    setUploading(true);
    setError(null);
    try {
      const result = await importsApi.confirm(preview.import_id, true);
      setLocationSummary(result.locations);
      toast({
        title: "Import complete",
        description: `${validation.import_job.success_count} companies added`,
        variant: "success",
      });
      setStep("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader title="Import companies" description="Upload an Excel or CSV file of prospects" />

      <ImportStepper steps={STEPS} current={step} />

      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}

      {step === "upload" && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
          }}
          className={
            "flex flex-col items-center justify-center rounded-xl border-2 border-dashed bg-white p-16 text-center transition-colors " +
            (dragActive ? "border-teal-400 bg-teal-50/40" : "border-navy-200")
          }
        >
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-navy-100 text-navy-500">
            <Upload className="h-5 w-5" />
          </div>
          <p className="mb-1 text-sm font-medium text-navy-700">Drag and drop your file here</p>
          <p className="mb-4 text-xs text-navy-400">Supports .xlsx, .xls, .csv</p>
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading}>
            {uploading ? "Uploading..." : "Choose file"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </div>
      )}

      {step === "map" && preview && (
        <div className="space-y-4">
          <p className="text-sm text-navy-600">
            <span className="font-semibold text-navy-900">{preview.row_count} rows</span> detected. Map spreadsheet
            columns to Meetings Manager fields.
          </p>
          <div className="overflow-hidden rounded-xl border border-navy-100 bg-white shadow-card">
            <table className="w-full text-sm">
              <thead className="bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
                <tr>
                  <th className="px-4 py-2">System field</th>
                  <th className="px-4 py-2">Spreadsheet column</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(MAPPABLE_FIELD_LABELS).map(([field, label]) => (
                  <tr key={field} className="border-t border-navy-100">
                    <td className="px-4 py-2 font-medium text-navy-800">{label}</td>
                    <td className="px-4 py-2">
                      <select
                        value={mapping[field] || ""}
                        onChange={(e) => setMapping((prev) => ({ ...prev, [field]: e.target.value }))}
                        className="w-full rounded-lg border border-navy-200 px-2 py-1.5 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
                      >
                        <option value="">Not mapped</option>
                        {preview.columns.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end">
            <Button onClick={handleValidate} disabled={uploading || !mapping.company_name}>
              {uploading ? "Validating..." : "Continue"}
            </Button>
          </div>
        </div>
      )}

      {step === "validate" && validation && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <StatCard label="Ready to import" value={validation.import_job.success_count} tone="success" />
            <StatCard label="Duplicates" value={validation.import_job.duplicate_count} tone="warning" />
            <StatCard label="Errors" value={validation.import_job.error_count} tone="danger" />
          </div>
          <div className="max-h-96 overflow-y-auto rounded-xl border border-navy-100 bg-white shadow-card">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
                <tr>
                  <th className="px-4 py-2">Row</th>
                  <th className="px-4 py-2">Company</th>
                  <th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {validation.rows.map((r) => (
                  <tr key={r.id} className="border-t border-navy-100">
                    <td className="px-4 py-2 text-navy-500">{r.row_number}</td>
                    <td className="px-4 py-2 text-navy-800">{r.mapped_data?.company_name || r.raw_data.name || "—"}</td>
                    <td className="px-4 py-2">
                      <ImportRowStatusBadge row={r} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setStep("map")}>
              Back
            </Button>
            <Button onClick={handleConfirm} disabled={uploading || validation.import_job.success_count === 0}>
              {uploading ? "Importing..." : `Import ${validation.import_job.success_count} records`}
            </Button>
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="rounded-xl border border-navy-100 bg-white p-10 text-center shadow-card">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-50 text-success">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <p className="mb-2 text-lg font-semibold text-navy-900">
            {locationSummary ? `${locationSummary.total} companies processed` : "Import complete"}
          </p>

          {locationSummary && (
            <div className="mx-auto mb-6 grid max-w-md grid-cols-2 gap-3 text-left sm:grid-cols-4">
              <LocationCountStat
                icon={<CheckCircle2 className="h-4 w-4" />}
                label="Verified"
                value={locationSummary.verified}
                tone="text-success"
              />
              <LocationCountStat
                icon={<HelpCircle className="h-4 w-4" />}
                label="Need review"
                value={locationSummary.needs_review}
                tone="text-warning"
              />
              <LocationCountStat
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Missing data"
                value={locationSummary.unverified}
                tone="text-navy-500"
              />
              <LocationCountStat
                icon={<XCircle className="h-4 w-4" />}
                label="Failed"
                value={locationSummary.failed}
                tone="text-danger"
              />
            </div>
          )}

          <div className="flex justify-center gap-2">
            {locationSummary && (locationSummary.needs_review > 0 || locationSummary.failed > 0) && (
              <Button
                variant="secondary"
                onClick={() => router.push("/admin/prospects?verification_status=needs_review")}
              >
                Review location issues
              </Button>
            )}
            <Button onClick={() => router.push("/admin/prospects")}>View prospects</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function LocationCountStat({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <div className="rounded-lg border border-navy-100 bg-navy-50/40 px-3 py-2">
      <div className={`flex items-center gap-1.5 text-xs font-medium ${tone}`}>
        {icon}
        {label}
      </div>
      <p className="mt-1 text-lg font-semibold text-navy-900">{value}</p>
    </div>
  );
}
