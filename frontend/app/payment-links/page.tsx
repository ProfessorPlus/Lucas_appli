"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CreditCard,
  Loader2,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  XCircle,
  CircleDot,
  ExternalLink,
} from "lucide-react";
import { toast } from "sonner";

import {
  api,
  type CreateLinksBody,
  type ExtractedFamily,
  type PaymentLinksList,
  type TeacherStripeStatus,
  type UnpaidN2Response,
} from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const PAYMENT_METHODS = ["card", "link", "apple_pay", "google_pay", "twint"];

export default function PaymentLinksPage() {
  // Shared state
  const [families, setFamilies] = useState<ExtractedFamily[]>([]);
  const [existing, setExisting] = useState<PaymentLinksList | null>(null);
  const [stripeStatuses, setStripeStatuses] = useState<TeacherStripeStatus[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);

  // Tab 1 — Generate
  const [noSplit, setNoSplit] = useState(true);
  const [methods, setMethods] = useState<Set<string>>(new Set(["card", "link", "apple_pay", "google_pay"]));
  const [skipIfExists, setSkipIfExists] = useState(true);
  const [includeN2, setIncludeN2] = useState(false);
  const [n2Year, setN2Year] = useState(new Date().getFullYear());
  const [n2Month, setN2Month] = useState(((new Date().getMonth() + 12 - 2) % 12) + 1);
  const [unpaidN2, setUnpaidN2] = useState<UnpaidN2Response | null>(null);
  const [loadingN2, setLoadingN2] = useState(false);

  // Tab 2 — Regenerate
  const [selectedForRegen, setSelectedForRegen] = useState<Set<string>>(new Set());

  // Submit
  const [submitting, setSubmitting] = useState(false);

  async function reload() {
    try {
      const [fams, existingLinks, statuses] = await Promise.all([
        api.get<ExtractedFamily[]>("/payment-links/families"),
        api.get<PaymentLinksList>("/payment-links/list"),
        api.get<TeacherStripeStatus[]>("/teachers/stripe-status"),
      ]);
      setFamilies(fams);
      setExisting(existingLinks);
      setStripeStatuses(statuses);
    } catch (e) {
      toast.error(`Erreur chargement : ${e instanceof Error ? e.message : "?"}`);
    }
  }
  useEffect(() => { void reload(); }, []);

  async function detectN2() {
    setLoadingN2(true);
    try {
      const r = await api.get<UnpaidN2Response>(
        `/payment-links/unpaid-detect?year=${n2Year}&month=${n2Month}`,
      );
      setUnpaidN2(r);
      if (r.success) toast.success(`${r.total_rows ?? 0} lignes impayées détectées pour ${r.month_label}`);
      else toast.error(`Échec : ${r.error}`);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally {
      setLoadingN2(false);
    }
  }

  async function launch(targetFamilyIds: string[] | null) {
    if (submitting) return;
    setSubmitting(true);
    setJobId(null);
    try {
      const body: CreateLinksBody = {
        no_split: noSplit,
        selected_teachers: null,
        payment_method_types: Array.from(methods),
        target_family_ids: targetFamilyIds,
        additional_amounts: includeN2 && unpaidN2?.families ? unpaidN2.families : null,
        skip_if_exists: skipIfExists,
      };
      const r = await api.post<{ job_id: string }>("/payment-links/create", body);
      setJobId(r.job_id);
      toast.success(`Job lancé — ${r.job_id.slice(0, 8)}`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSubmitting(false);
    }
  }

  const stripeWarnings = useMemo(
    () => stripeStatuses.filter((s) => s.status !== "active" && s.status !== "unconfigured"),
    [stripeStatuses],
  );
  const stripeActive = stripeStatuses.filter((s) => s.status === "active").length;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<CreditCard className="h-6 w-6" />}
        title="Liens de paiement Stripe"
        subtitle="Génère les liens à envoyer aux familles. Avec ou sans split vers les profs."
      />

      {/* ── Stripe Connect status summary ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="h-4 w-4 text-success" />
            Comptes Stripe Connect
          </CardTitle>
          <CardDescription>
            {stripeActive}/{stripeStatuses.length} actifs
            {stripeWarnings.length > 0 && ` · ${stripeWarnings.length} en attention`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-1.5">
            {stripeStatuses.map((s) => (
              <StripeBadge key={s.name} status={s} />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── Existing links (read-only) ── */}
      {existing?.exists && existing.count > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Liens existants</CardTitle>
            <CardDescription>
              {existing.count} liens dans <code className="text-xs bg-secondary px-1 rounded">payment_links_output.json</code> ({existing.source}).
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* ── Tabs ── */}
      <Tabs defaultValue="generate">
        <TabsList>
          <TabsTrigger value="generate">Générer (toutes)</TabsTrigger>
          <TabsTrigger value="regenerate">Régénérer (sélection)</TabsTrigger>
        </TabsList>

        {/* ── Tab Generate ── */}
        <TabsContent value="generate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mode</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <Label htmlFor="no-split" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
                    Mode <strong>NO-SPLIT</strong> — tout encaisse sur le compte principal
                  </Label>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Désactive si tu veux des transferts automatiques vers chaque prof (Stripe Connect).
                  </p>
                </div>
                <Switch id="no-split" checked={noSplit} onCheckedChange={setNoSplit} />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <Label htmlFor="skip" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
                    Ignorer les familles déjà liées
                  </Label>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Évite de recréer un lien existant dans <code>payment_links_output.json</code>.
                  </p>
                </div>
                <Switch id="skip" checked={skipIfExists} onCheckedChange={setSkipIfExists} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Méthodes de paiement</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              {PAYMENT_METHODS.map((m) => (
                <label key={m} className="flex items-center gap-2 cursor-pointer">
                  <Checkbox
                    checked={methods.has(m)}
                    onCheckedChange={(c) => {
                      const next = new Set(methods);
                      if (c) next.add(m);
                      else next.delete(m);
                      setMethods(next);
                    }}
                  />
                  <span className="text-sm font-medium">
                    {m === "card" ? "Carte" : m === "apple_pay" ? "Apple Pay" : m === "google_pay" ? "Google Pay" : m === "link" ? "Stripe Link" : "Twint"}
                  </span>
                </label>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Inclure impayés n-2</CardTitle>
              <CardDescription>
                Cumule les montants impayés des mois précédents (depuis Notion) avec le montant du mois courant.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-3">
                <Switch id="n2" checked={includeN2} onCheckedChange={setIncludeN2} />
                <Label htmlFor="n2" className="cursor-pointer normal-case tracking-normal text-sm">
                  Activer
                </Label>
              </div>
              {includeN2 && (
                <div className="space-y-3 rounded-lg border border-border p-3">
                  <div className="flex items-end gap-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="n2-year">Année</Label>
                      <Input
                        id="n2-year"
                        type="number"
                        value={n2Year}
                        onChange={(e) => setN2Year(parseInt(e.target.value, 10))}
                        className="w-24"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="n2-month">Mois</Label>
                      <Input
                        id="n2-month"
                        type="number"
                        min={1}
                        max={12}
                        value={n2Month}
                        onChange={(e) => setN2Month(parseInt(e.target.value, 10))}
                        className="w-20"
                      />
                    </div>
                    <Button variant="outline" size="sm" onClick={detectN2} disabled={loadingN2}>
                      {loadingN2 ? <Loader2 className="animate-spin" /> : <RefreshCw />} Détecter
                    </Button>
                  </div>
                  {unpaidN2 && unpaidN2.success && (
                    <div className="rounded-lg bg-secondary/50 p-3 text-sm">
                      <p className="font-medium">
                        {Object.keys(unpaidN2.families).length} famille(s) avec impayés en {unpaidN2.month_label}
                      </p>
                      <ul className="mt-1.5 max-h-32 overflow-y-auto space-y-0.5 text-xs">
                        {Object.entries(unpaidN2.families).map(([k, f]) => (
                          <li key={k} className="font-mono">
                            {f.parent_name} — {f.total_amount.toFixed(2)} {f.currency}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button
              variant="accent"
              size="lg"
              onClick={() => launch(null)}
              disabled={submitting || !!jobId}
            >
              {submitting ? <Loader2 className="animate-spin" /> : <Sparkles />}
              Générer les liens
            </Button>
          </div>
        </TabsContent>

        {/* ── Tab Regenerate ── */}
        <TabsContent value="regenerate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sélectionner les familles à régénérer</CardTitle>
              <CardDescription>
                Les anciens liens Stripe seront désactivés et remplacés par les nouveaux.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="w-10 p-3">
                        <Checkbox
                          checked={selectedForRegen.size === families.length && families.length > 0}
                          onCheckedChange={(c) => {
                            if (c) setSelectedForRegen(new Set(families.map((f) => f.family_id)));
                            else setSelectedForRegen(new Set());
                          }}
                        />
                      </th>
                      <th className="p-3 text-left font-semibold">Famille</th>
                      <th className="p-3 text-right font-semibold">Leçons</th>
                      <th className="p-3 text-center font-semibold">Devise</th>
                    </tr>
                  </thead>
                  <tbody>
                    {families.map((f) => (
                      <tr key={f.family_id} className="border-t border-border">
                        <td className="p-3">
                          <Checkbox
                            checked={selectedForRegen.has(f.family_id)}
                            onCheckedChange={(c) => {
                              const next = new Set(selectedForRegen);
                              if (c) next.add(f.family_id);
                              else next.delete(f.family_id);
                              setSelectedForRegen(next);
                            }}
                          />
                        </td>
                        <td className="p-3 font-medium">{f.parent_name}</td>
                        <td className="p-3 text-right tabular-nums">{f.lessons}</td>
                        <td className="p-3 text-center">
                          {f.currency && <Badge variant="secondary" className="text-[10px]">{f.currency}</Badge>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {selectedForRegen.size} famille(s) sélectionnée(s)
            </p>
            <Button
              variant="accent"
              size="lg"
              onClick={() => launch(Array.from(selectedForRegen))}
              disabled={submitting || !!jobId || selectedForRegen.size === 0}
            >
              {submitting ? <Loader2 className="animate-spin" /> : <RefreshCw />}
              Régénérer ({selectedForRegen.size})
            </Button>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── Job display ── */}
      {jobId && (
        <Card>
          <CardHeader>
            <CardTitle>Job en cours</CardTitle>
          </CardHeader>
          <CardContent>
            <JobRunner
              jobId={jobId}
              onDone={async () => {
                toast.success("Liens générés 🎉");
                await reload();
              }}
              onError={(err) => toast.error(`Échec : ${err}`)}
              onCancel={() => setJobId(null)}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StripeBadge({ status }: { status: TeacherStripeStatus }) {
  const map = {
    active: { tone: "success" as const, icon: CheckCircle2 },
    pending: { tone: "warning" as const, icon: AlertCircle },
    incomplete: { tone: "warning" as const, icon: AlertCircle },
    unconfigured: { tone: "secondary" as const, icon: CircleDot },
    error: { tone: "destructive" as const, icon: XCircle },
    no_stripe_key: { tone: "warning" as const, icon: AlertCircle },
    stripe_not_installed: { tone: "warning" as const, icon: AlertCircle },
  } as const;
  const m = map[status.status];
  const Icon = m.icon;
  return (
    <Badge variant={m.tone} className="text-[10px]">
      <Icon className="h-3 w-3" /> {status.name}
    </Badge>
  );
}
