"use client";

import { useState } from "react";
import { BookOpen, CheckCircle2, Printer } from "lucide-react";
import { SOPS, type Sop } from "@/content/sop";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

/** Standard Operating Procedures — content lives in src/content/sop.ts. */
export function SopLibrary() {
  const [activeId, setActiveId] = useState(SOPS[0]?.id);
  const sop = SOPS.find((s) => s.id === activeId) ?? SOPS[0];

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="Standard Operating Procedures"
        description="How we work: step-by-step procedures for the sales team."
        actions={
          <Button variant="secondary" onClick={() => window.print()}>
            <Printer className="h-4 w-4" /> Print
          </Button>
        }
      />

      <div className="flex flex-col gap-5 md:flex-row">
        {SOPS.length > 1 && (
          <nav className="shrink-0 space-y-1 md:w-56">
            {SOPS.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveId(s.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors",
                  s.id === sop.id ? "bg-white text-navy-900 shadow-card" : "text-navy-500 hover:bg-white/60 hover:text-navy-800"
                )}
              >
                <BookOpen className="h-4 w-4 shrink-0" />
                {s.title}
              </button>
            ))}
          </nav>
        )}
        {sop ? <SopDocument sop={sop} /> : <p className="text-sm text-navy-500">No procedures yet.</p>}
      </div>
    </div>
  );
}

function SopDocument({ sop }: { sop: Sop }) {
  return (
    <Card className="min-w-0 flex-1">
      <div className="border-b border-navy-100 px-6 py-5">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-navy-900">{sop.title}</h2>
          {sop.sample && <Badge tone="warning">Sample, not yet approved</Badge>}
        </div>
        <p className="text-sm text-navy-600">{sop.summary}</p>
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-navy-500">
          <div><dt className="inline">Owner: </dt><dd className="inline font-medium text-navy-700">{sop.owner}</dd></div>
          <div><dt className="inline">Version: </dt><dd className="inline font-medium text-navy-700">{sop.version}</dd></div>
          <div><dt className="inline">Last reviewed: </dt><dd className="inline font-medium text-navy-700">{sop.lastReviewed}</dd></div>
          <div><dt className="inline">Applies to: </dt><dd className="inline font-medium text-navy-700">{sop.audience}</dd></div>
        </dl>
      </div>
      <CardBody className="space-y-6 px-6 py-5">
        {sop.sections.map((section) => (
          <section key={section.heading}>
            <h3 className="mb-2 text-sm font-semibold text-navy-800">{section.heading}</h3>
            <ol className="space-y-3">
              {section.steps.map((step) => (
                <li key={step.title} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-teal-500" />
                  <div className="text-sm">
                    <p className="font-medium text-navy-800">{step.title}</p>
                    {step.details && (
                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-navy-600">
                        {step.details.map((d) => (
                          <li key={d}>{d}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </CardBody>
    </Card>
  );
}
