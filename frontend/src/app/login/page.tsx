"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { MapPin } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      router.push(user.role === "admin" ? "/admin" : "/sales");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-navy-950 px-4">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            "radial-gradient(circle at 20% 20%, rgba(38,166,156,0.25), transparent 45%), radial-gradient(circle at 80% 70%, rgba(38,166,156,0.15), transparent 40%)",
        }}
      />
      <div className="relative w-full max-w-sm rounded-xl border border-white/10 bg-white p-8 shadow-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-navy-900 text-teal-400">
            <MapPin className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-semibold text-navy-900">Meetings Manager</h1>
          <p className="mt-1 text-sm text-navy-500">Sam IT Solutions · Field Sales</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-navy-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-navy-200 px-3 py-2.5 text-sm text-navy-900 outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
              placeholder="you@samitsolutions.com"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-navy-700">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-navy-200 px-3 py-2.5 text-sm text-navy-900 outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring"
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>
          )}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
