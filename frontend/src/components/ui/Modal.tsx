"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import { cn } from "@/lib/utils";

export function Modal({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (open) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 px-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white shadow-xl animate-slide-up",
          className
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-navy-100 px-5 py-4">
            <h2 className="text-base font-semibold text-navy-900">{title}</h2>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-navy-400 transition-colors hover:bg-navy-100 hover:text-navy-700"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      {description && <p className="mb-5 text-sm text-navy-600">{description}</p>}
      <div className="flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg border border-navy-200 px-4 py-2 text-sm font-medium text-navy-700 transition-colors hover:bg-navy-50"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors",
            danger ? "bg-danger hover:opacity-90" : "bg-navy-900 hover:bg-navy-800"
          )}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
