"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Search } from "lucide-react";
import { locationsApi } from "@/lib/api/locations";
import type { LocationCandidate } from "@/types";
import { cn } from "@/lib/utils";

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

export function LocationSearchInput({
  placeholder = "Search address or place name...",
  onSelect,
  className,
}: {
  placeholder?: string;
  onSelect: (candidate: LocationCandidate) => void;
  className?: string;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LocationCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    debounceRef.current = setTimeout(async () => {
      const requestId = ++requestIdRef.current;
      try {
        const { candidates } = await locationsApi.search(trimmed);
        if (requestId !== requestIdRef.current) return; // a newer keystroke superseded this request
        setResults(candidates);
        setOpen(true);
      } catch (err) {
        if (requestId !== requestIdRef.current) return;
        setResults([]);
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        if (requestId === requestIdRef.current) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleSelect(candidate: LocationCandidate) {
    onSelect(candidate);
    setQuery(candidate.name || candidate.formatted_address);
    setOpen(false);
    setResults([]);
  }

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-400" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-navy-200 py-1.5 pl-8 pr-8 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
        />
        {loading && (
          <Loader2 className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-navy-400" />
        )}
      </div>

      {open && (results.length > 0 || error) && (
        <div className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-navy-100 bg-white shadow-lg">
          {error ? (
            <p className="px-3 py-2 text-xs text-danger">{error}</p>
          ) : (
            results.map((candidate, i) => (
              <button
                key={`${candidate.place_id ?? i}`}
                type="button"
                onClick={() => handleSelect(candidate)}
                className="flex w-full items-start gap-2 border-b border-navy-50 px-3 py-2 text-left text-sm last:border-b-0 hover:bg-navy-50"
              >
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />
                <span>
                  {candidate.name && <span className="block font-medium text-navy-800">{candidate.name}</span>}
                  <span className="block text-xs text-navy-500">{candidate.formatted_address}</span>
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
