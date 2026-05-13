"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Plus,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  XCircle,
  CircleDot,
  Save,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { api, type Teacher, type TeacherStripeStatus } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/EmptyState";
import { cn } from "@/lib/utils";

export default function TeachersPage() {
  const [teachers, setTeachers] = useState<Teacher[] | null>(null);
  const [statuses, setStatuses] = useState<Record<string, TeacherStripeStatus>>({});
  const [statusLoading, setStatusLoading] = useState<Record<string, boolean>>({});
  const [editing, setEditing] = useState<Teacher | null>(null);
  const [creating, setCreating] = useState(false);

  const reload = useCallback(async () => {
    try {
      const list = await api.get<Teacher[]>("/settings/teachers");
      setTeachers(list);
    } catch (e) {
      toast.error("Impossible de charger les professeurs");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function probeStripe(name: string) {
    setStatusLoading((s) => ({ ...s, [name]: true }));
    try {
      const r = await api.get<TeacherStripeStatus>(
        `/settings/teachers/${encodeURIComponent(name)}/stripe-status`,
      );
      setStatuses((s) => ({ ...s, [name]: r }));
    } catch (e) {
      toast.error(`Stripe check failed for ${name}`);
    } finally {
      setStatusLoading((s) => ({ ...s, [name]: false }));
    }
  }

  async function remove(name: string) {
    if (!confirm(`Supprimer le professeur "${name}" ?`)) return;
    try {
      await api.delete(`/settings/teachers/${encodeURIComponent(name)}`);
      toast.success(`${name} supprimé`);
      await reload();
    } catch (e) {
      toast.error(`Échec suppression : ${e instanceof Error ? e.message : "?"}`);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Professeurs</h2>
          <p className="text-sm text-muted-foreground">
            Taux horaires (CHF/EUR), comptes Stripe Connect, et option Auto-CHF.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} variant="accent">
          <Plus /> Ajouter
        </Button>
      </div>

      {creating && (
        <TeacherForm
          mode="create"
          onCancel={() => setCreating(false)}
          onSaved={async () => {
            setCreating(false);
            await reload();
          }}
        />
      )}

      {teachers === null ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </CardContent>
        </Card>
      ) : teachers.length === 0 ? (
        <EmptyState
          title="Aucun professeur"
          description="Ajoute ton premier professeur."
          action={<Button onClick={() => setCreating(true)} variant="accent"><Plus /> Ajouter</Button>}
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-3 text-left font-semibold">Nom</th>
                  <th className="p-3 text-right font-semibold">CHF/h</th>
                  <th className="p-3 text-right font-semibold">EUR/h</th>
                  <th className="p-3 text-center font-semibold">Auto-CHF</th>
                  <th className="p-3 text-left font-semibold">Stripe Connect</th>
                  <th className="p-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((t) => {
                  const st = statuses[t.name];
                  return (
                    <tr key={t.name} className="border-t border-border">
                      <td className="p-3 font-medium">{t.name}</td>
                      <td className="p-3 text-right tabular-nums">
                        {t.pay_rate_chf > 0 ? t.pay_rate_chf.toFixed(2) : "—"}
                      </td>
                      <td className="p-3 text-right tabular-nums">
                        {t.pay_rate_eur > 0 ? t.pay_rate_eur.toFixed(2) : "—"}
                      </td>
                      <td className="p-3 text-center">
                        {t.auto_chf ? (
                          <Badge variant="accent" className="text-[10px]">ON</Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="p-3">
                        <StripeStatusBadge
                          accountId={t.connect_account_id}
                          status={st}
                          loading={statusLoading[t.name]}
                          onProbe={() => probeStripe(t.name)}
                        />
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button variant="ghost" size="sm" onClick={() => setEditing(t)}>
                            Modifier
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => remove(t.name)}
                            aria-label={`Supprimer ${t.name}`}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {editing && (
        <TeacherForm
          mode="edit"
          initial={editing}
          onCancel={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await reload();
          }}
        />
      )}
    </div>
  );
}

function StripeStatusBadge({
  accountId,
  status,
  loading,
  onProbe,
}: {
  accountId: string;
  status?: TeacherStripeStatus;
  loading?: boolean;
  onProbe: () => void;
}) {
  if (!accountId) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Probing…
      </span>
    );
  }
  if (!status) {
    return (
      <Button variant="ghost" size="sm" onClick={onProbe} className="text-xs">
        <CircleDot className="h-3 w-3" /> Tester
      </Button>
    );
  }
  const map = {
    active: { tone: "success" as const, icon: CheckCircle2, label: "Active" },
    pending: { tone: "warning" as const, icon: AlertCircle, label: "Pending" },
    incomplete: { tone: "warning" as const, icon: AlertCircle, label: "Incomplet" },
    unconfigured: { tone: "secondary" as const, icon: CircleDot, label: "Non configuré" },
    error: { tone: "destructive" as const, icon: XCircle, label: "Erreur" },
    no_stripe_key: { tone: "warning" as const, icon: AlertCircle, label: "Clé Stripe absente" },
    stripe_not_installed: { tone: "warning" as const, icon: AlertCircle, label: "Stripe SDK manquant" },
  };
  const m = map[status.status];
  const Icon = m.icon;
  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <Badge variant={m.tone} className="text-[10px]">
        <Icon className="h-3 w-3" />
        {m.label}
      </Badge>
      <code className="font-mono text-[10px] text-muted-foreground">{accountId.slice(0, 14)}…</code>
    </span>
  );
}

function TeacherForm({
  mode,
  initial,
  onCancel,
  onSaved,
}: {
  mode: "create" | "edit";
  initial?: Teacher;
  onCancel: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [accountId, setAccountId] = useState(initial?.connect_account_id ?? "");
  const [chf, setChf] = useState(initial?.pay_rate_chf?.toString() ?? "0");
  const [eur, setEur] = useState(initial?.pay_rate_eur?.toString() ?? "0");
  const [autoChf, setAutoChf] = useState(initial?.auto_chf ?? false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        name,
        connect_account_id: accountId,
        pay_rate_chf: parseFloat(chf) || 0,
        pay_rate_eur: parseFloat(eur) || 0,
        auto_chf: autoChf,
      };
      if (mode === "create") {
        await api.post("/settings/teachers", payload);
        toast.success(`Professeur "${name}" créé`);
      } else {
        // edit: PATCH everything except name
        await api.patch(`/settings/teachers/${encodeURIComponent(initial!.name)}`, {
          connect_account_id: accountId,
          pay_rate_chf: payload.pay_rate_chf,
          pay_rate_eur: payload.pay_rate_eur,
          auto_chf: autoChf,
        });
        toast.success(`"${initial!.name}" mis à jour`);
      }
      await onSaved();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="border-accent/30">
      <CardHeader>
        <CardTitle>{mode === "create" ? "Ajouter un professeur" : `Modifier "${initial?.name}"`}</CardTitle>
        <CardDescription>
          Taux horaire par devise. Auto-CHF ajuste automatiquement le taux CHF en fonction du taux EUR cible.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="t-name">Nom</Label>
            <Input
              id="t-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={mode === "edit"}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-acc">Stripe Connect Account ID</Label>
            <Input
              id="t-acc"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              placeholder="acct_..."
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-chf">Taux CHF/h</Label>
            <Input id="t-chf" type="number" step="0.01" value={chf} onChange={(e) => setChf(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-eur">Taux EUR/h</Label>
            <Input id="t-eur" type="number" step="0.01" value={eur} onChange={(e) => setEur(e.target.value)} />
          </div>
          <div className="flex items-center gap-2 sm:col-span-2">
            <Switch id="t-auto" checked={autoChf} onCheckedChange={setAutoChf} />
            <Label htmlFor="t-auto" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
              Auto-CHF (recalcule CHF à partir de l'EUR cible)
            </Label>
          </div>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={onCancel}>
              <X /> Annuler
            </Button>
            <Button type="submit" disabled={submitting || !name}>
              {submitting ? <Loader2 className="animate-spin" /> : <Save />} Enregistrer
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
