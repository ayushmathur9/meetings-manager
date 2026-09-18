"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { usersApi } from "@/lib/api/users";
import type { User } from "@/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/layout/PageHeader";
import { useToast } from "@/components/ui/Toast";

const inputClass =
  "w-full rounded-lg border border-navy-200 px-3 py-2 text-sm outline-none transition-colors focus:border-teal-500 focus-visible:shadow-focus-ring";

export default function TeamPage() {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "salesperson">("salesperson");
  const [error, setError] = useState<string | null>(null);

  function load() {
    usersApi.list().then(setUsers);
  }

  useEffect(load, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/users", { name, email, password, role });
      toast({ title: "Team member added", description: name, variant: "success" });
      setName("");
      setEmail("");
      setPassword("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    }
  }

  return (
    <div className="p-6">
      <PageHeader title="Team" description="Manage admin and salesperson accounts" />

      <div className="grid grid-cols-3 gap-6">
        <Card className="col-span-2 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-navy-50 text-left text-xs uppercase tracking-wide text-navy-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-navy-100">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={u.name} size="sm" />
                      <span className="font-medium text-navy-900">{u.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-navy-600">{u.email}</td>
                  <td className="px-4 py-3">
                    <Badge tone={u.role === "admin" ? "info" : "neutral"}>{u.role}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-navy-800">Add team member</h2>
          </CardHeader>
          <CardBody>
            <form onSubmit={handleSubmit} className="space-y-3">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Full name"
                required
                className={inputClass}
              />
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                type="email"
                required
                className={inputClass}
              />
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Temporary password"
                type="password"
                required
                className={inputClass}
              />
              <select value={role} onChange={(e) => setRole(e.target.value as "admin" | "salesperson")} className={inputClass}>
                <option value="salesperson">Salesperson</option>
                <option value="admin">Admin</option>
              </select>
              {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}
              <Button type="submit" className="w-full">
                Add member
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
