"use client";

import { useCallback, useEffect, useState } from "react";
import { Zap, Loader2, RefreshCw, CheckCircle2, AlertCircle, XCircle, CircleDot } from "lucide-react";
import { toast } from "sonner";

import { api, type TwintAccount, type TwintConnectAccount, type TwintStatusResponse } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

/** Mappe la capability Stripe `twint_payments` sur un badge lisible. */
function statusBadge(raw: string) {
  const s = (raw || "").toLowerCase();
  if (s === "active") return { tone: "success" as const, Icon: CheckCircle2, label: "Active" };
  if (s === "pending") return { tone: "warning" as const, Icon: AlertCircle, label: "En attente" };
  if (s === "inactive") return { tone: "secondary" as const, Icon: CircleDot, label: "Inactive" };
  if (s.startsWith("erreur")) return { tone: "destructive" as const, Icon: XCircle, label: raw };
  return { tone: "secondary" as const, Icon: CircleDot, label: raw || "non configuré" };
}

export default function TwintPage() {
  const [accounts, setAccounts] = useState<TwintAccount[] | null>(null);
  const [connectAccounts, setConnectAccounts] = useState<TwintConnectAccount[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    try {
      const list = await api.get<TwintConnectAccount[]>("/twint/accounts");
      setConnectAccounts(list);
      setSelected(new Set(list.map((a) => a.connect_account_id)));
    } catch {
      toast.error("Impossible de charger les comptes Connect");
    }
  }, []);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const checkStatus = useCallback(async () => {
    setChecking(true);
    try {
      const r = await api.get<TwintStatusResponse>("/twint/status");
      if (!r.success) {
        toast.error(r.error || "Erreur Stripe");
        setAccounts(null);
        return;
      }
      setAccounts(r.accounts);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally {
      setChecking(false);
    }
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function activate() {
    const ids = connectAccounts
      .map((a) => a.connect_account_id)
      .filter((id) => selected.has(id));
    if (ids.length === 0) {
      toast.error("Sélectionne au moins un compte");
      return;
    }
    if (!confirm(`Demander l'activation de Twint sur ${ids.length} compte(s) Stripe Connect ?`)) return;
    setSubmitting(true);
    setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/twint/activate", { account_ids: ids });
      setJobId(r.job_id);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSubmitting(false);
    }
  }

  const allSelected = connectAccounts.length > 0 && selected.size === connectAccounts.length;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Zap className="h-6 w-6" />}
        title="Activation Twint"
        subtitle="Demande la capability twint_payments sur les comptes Stripe Connect des professeurs."
      />

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4 space-y-0">
          <div>
            <CardTitle>Statut des comptes</CardTitle>
            <CardDescription>
              Interroge Stripe pour chaque professeur configuré dans secrets.yaml.
            </CardDescription>
          </div>
          <Button onClick={checkStatus} disabled={checking} variant="secondary">
            {checking ? <Loader2 className="animate-spin" /> : <RefreshCw />} Vérifier
          </Button>
        </CardHeader>
        <CardContent>
          {accounts === null ? (
            <p className="py-4 text-sm text-muted-foreground">
              Lance une vérification pour afficher le statut Twint de chaque compte.
            </p>
          ) : accounts.length === 0 ? (
            <EmptyState title="Aucun professeur" description="secrets.yaml ne contient aucun professeur." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="p-3 text-left font-semibold">Professeur</th>
                    <th className="p-3 text-left font-semibold">Compte Connect</th>
                    <th className="p-3 text-left font-semibold">Twint</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => {
                    const b = statusBadge(a.twint_status);
                    const Icon = b.Icon;
                    return (
                      <tr key={a.name} className="border-t border-border">
                        <td className="p-3 font-medium">{a.name}</td>
                        <td className="p-3">
                          {a.connect_id ? (
                            <code className="font-mono text-[11px] text-muted-foreground">{a.connect_id}</code>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="p-3">
                          {a.has_connect ? (
                            <Badge variant={b.tone} className="text-[10px]">
                              <Icon className="h-3 w-3" />
                              {b.label}
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">Pas de compte Connect</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Activer Twint</CardTitle>
          <CardDescription>
            Seuls les professeurs disposant d&apos;un compte Connect peuvent être activés.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {connectAccounts.length === 0 ? (
            <EmptyState
              title="Aucun compte Connect configuré"
              description="Renseigne un Stripe Connect Account ID dans Paramètres → Professeurs."
            />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="twint-all"
                  checked={allSelected}
                  onCheckedChange={(c) =>
                    setSelected(c ? new Set(connectAccounts.map((a) => a.connect_account_id)) : new Set())
                  }
                />
                <Label
                  htmlFor="twint-all"
                  className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground"
                >
                  Tout sélectionner ({selected.size}/{connectAccounts.length})
                </Label>
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                {connectAccounts.map((a) => (
                  <label
                    key={a.connect_account_id}
                    className="flex cursor-pointer items-center gap-2 rounded-lg border border-border p-3 transition-colors hover:border-accent/40"
                  >
                    <Checkbox
                      checked={selected.has(a.connect_account_id)}
                      onCheckedChange={() => toggle(a.connect_account_id)}
                    />
                    <span className="flex-1">
                      <span className="block text-sm font-medium">{a.name}</span>
                      <code className="font-mono text-[10px] text-muted-foreground">
                        {a.connect_account_id}
                      </code>
                    </span>
                  </label>
                ))}
              </div>

              <div className="flex justify-end">
                <Button onClick={activate} disabled={submitting || selected.size === 0}>
                  {submitting ? <Loader2 className="animate-spin" /> : <Zap />} Activer Twint
                </Button>
              </div>
            </>
          )}

          {jobId && (
            <JobRunner
              jobId={jobId}
              onDone={(r: { activated?: number; errors?: string[] }) => {
                toast.success(`${r?.activated ?? 0} compte(s) traité(s)`);
                (r?.errors ?? []).forEach((err) => toast.warning(err));
                void checkStatus();
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
