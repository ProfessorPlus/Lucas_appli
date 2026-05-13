"use client";

import { useState } from "react";
import { RefreshCw, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function SyncPage() {
  const [noSplit, setNoSplit] = useState(true);
  const [usePeriod, setUsePeriod] = useState(false);
  const [sinceDate, setSinceDate] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function launch() {
    setSubmitting(true); setJobId(null);
    try {
      const body = {
        mode: noSplit ? "no-split" : "normal",
        since_date: usePeriod && sinceDate ? sinceDate : null,
      };
      const r = await api.post<{ job_id: string }>("/sync/stripe-to-notion", body);
      setJobId(r.job_id);
      toast.success(`Sync lancée`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<RefreshCw className="h-6 w-6" />}
        title="Sync Stripe → Notion"
        subtitle="Marque les lignes Notion comme 'Payé' à partir des charges Stripe."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mode</CardTitle>
          <CardDescription>
            NO-SPLIT pour comptes encaissés sur l'unique compte principal (recommandé).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
            <Label htmlFor="ns" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
              Mode NO-SPLIT
            </Label>
            <Switch id="ns" checked={noSplit} onCheckedChange={setNoSplit} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Période</CardTitle>
          <CardDescription>
            Optionnel — par défaut, scan complet des charges récentes Stripe.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <Switch checked={usePeriod} onCheckedChange={setUsePeriod} />
            <span className="text-sm">Filtrer depuis une date</span>
          </div>
          {usePeriod && (
            <div className="space-y-1.5">
              <Label>Depuis</Label>
              <Input type="date" value={sinceDate} onChange={(e) => setSinceDate(e.target.value)} className="w-48" />
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button variant="accent" size="lg" onClick={launch} disabled={submitting || !!jobId}>
          {submitting ? <Loader2 className="animate-spin" /> : <Sparkles />} Lancer la sync
        </Button>
      </div>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Sync terminée 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
