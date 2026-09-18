"use client";

import { FormEvent, useEffect, useState } from "react";
import { Star, Trash2 } from "lucide-react";
import { api } from "@/lib/api/client";
import type { LocationCandidate, NamedLocation, OrgSettingsOut } from "@/types";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadingSkeleton } from "@/components/ui/Spinner";
import { LocationSearchInput } from "@/components/locations/LocationSearchInput";
import { useToast } from "@/components/ui/Toast";

type OrgSettings = OrgSettingsOut;

const inputClass =
  "w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring";

export default function SettingsPage() {
  const toast = useToast();
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [newLocationName, setNewLocationName] = useState("");
  const [pendingCandidate, setPendingCandidate] = useState<LocationCandidate | null>(null);

  useEffect(() => {
    api.get<OrgSettings>("/settings").then(setSettings);
  }, []);

  function handleLocationFound(candidate: LocationCandidate) {
    setPendingCandidate(candidate);
    setNewLocationName(candidate.name || candidate.formatted_address);
  }

  function handleAddLocation() {
    if (!settings || !pendingCandidate || !newLocationName.trim()) return;
    const location: NamedLocation = {
      name: newLocationName.trim(),
      address: pendingCandidate.formatted_address,
      latitude: pendingCandidate.latitude,
      longitude: pendingCandidate.longitude,
    };
    const existing = settings.saved_locations ?? [];
    const next = [...existing.filter((l) => l.name !== location.name), location];
    setSettings({ ...settings, saved_locations: next });
    setPendingCandidate(null);
    setNewLocationName("");
  }

  function handleRemoveLocation(name: string) {
    if (!settings) return;
    const next = (settings.saved_locations ?? []).filter((l) => l.name !== name);
    const clearDefault = settings.default_start_location?.name === name;
    setSettings({
      ...settings,
      saved_locations: next,
      default_start_location: clearDefault ? null : settings.default_start_location,
    });
  }

  function handleSetDefault(location: NamedLocation) {
    if (!settings) return;
    setSettings({ ...settings, default_start_location: location });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    try {
      await api.patch("/settings", settings);
      toast({ title: "Settings saved", variant: "success" });
    } catch (err) {
      toast({ title: "Couldn't save settings", description: err instanceof Error ? err.message : undefined, variant: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-6">
        <LoadingSkeleton className="h-8 w-48" />
        <LoadingSkeleton className="h-40 w-full" />
        <LoadingSkeleton className="h-32 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <PageHeader title="Settings" description="Organization defaults for scheduling and routing" />

      <form onSubmit={handleSubmit} className="space-y-5">
        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Organization</h2>
          </CardHeader>
          <CardBody>
            <label className="mb-1 block text-xs font-medium text-navy-600">Organization name</label>
            <input
              value={settings.org_name}
              onChange={(e) => setSettings({ ...settings, org_name: e.target.value })}
              className={inputClass}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Scheduling defaults</h2>
          </CardHeader>
          <CardBody className="flex gap-4">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-navy-600">Default meeting duration (min)</label>
              <input
                type="number"
                value={settings.default_meeting_duration_minutes}
                onChange={(e) => setSettings({ ...settings, default_meeting_duration_minutes: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-navy-600">Travel buffer (min)</label>
              <input
                type="number"
                value={settings.default_travel_buffer_minutes}
                onChange={(e) => setSettings({ ...settings, default_travel_buffer_minutes: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Working hours</h2>
          </CardHeader>
          <CardBody className="flex gap-4">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-navy-600">Start</label>
              <input
                type="time"
                value={settings.working_hours_start}
                onChange={(e) => setSettings({ ...settings, working_hours_start: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-navy-600">End</label>
              <input
                type="time"
                value={settings.working_hours_end}
                onChange={(e) => setSettings({ ...settings, working_hours_end: e.target.value })}
                className={inputClass}
              />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Saved locations</h2>
          </CardHeader>
          <CardBody>
            <p className="mb-3 text-xs text-navy-500">
              Search for an address or place to save it as a reusable starting location for route planning.
            </p>
            <div className="mb-3 flex items-start gap-2">
              <div className="flex-1">
                <LocationSearchInput onSelect={handleLocationFound} placeholder="Search address or place name..." />
              </div>
            </div>
            {pendingCandidate && (
              <div className="mb-4 flex items-end gap-2 rounded-lg border border-teal-200 bg-teal-50/50 p-3">
                <div className="flex-1">
                  <label className="mb-1 block text-xs font-medium text-navy-600">Save as</label>
                  <input
                    value={newLocationName}
                    onChange={(e) => setNewLocationName(e.target.value)}
                    className={inputClass}
                    placeholder="e.g. Sam IT Solutions Office"
                  />
                  <p className="mt-1 text-xs text-navy-500">{pendingCandidate.formatted_address}</p>
                </div>
                <Button type="button" size="sm" onClick={handleAddLocation} disabled={!newLocationName.trim()}>
                  Add
                </Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => setPendingCandidate(null)}>
                  Cancel
                </Button>
              </div>
            )}

            {settings.saved_locations && settings.saved_locations.length > 0 ? (
              <ul className="divide-y divide-navy-100 rounded-lg border border-navy-100">
                {settings.saved_locations.map((loc) => {
                  const isDefault = settings.default_start_location?.name === loc.name;
                  return (
                    <li key={loc.name} className="flex items-center justify-between gap-2 px-3 py-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-navy-800">{loc.name}</p>
                        <p className="truncate text-xs text-navy-500">
                          {loc.address || `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleSetDefault(loc)}
                          title={isDefault ? "Default start location" : "Set as default start location"}
                          className={`flex h-7 w-7 items-center justify-center rounded-lg transition-colors ${
                            isDefault ? "text-amber-500" : "text-navy-300 hover:text-amber-500"
                          }`}
                        >
                          <Star className="h-4 w-4" fill={isDefault ? "currentColor" : "none"} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRemoveLocation(loc.name)}
                          title="Remove"
                          className="flex h-7 w-7 items-center justify-center rounded-lg text-navy-300 transition-colors hover:text-danger"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-xs text-navy-400">No saved locations yet.</p>
            )}
          </CardBody>
        </Card>

        <Button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save settings"}
        </Button>
      </form>
    </div>
  );
}
