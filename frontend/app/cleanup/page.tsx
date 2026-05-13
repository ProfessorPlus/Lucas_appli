"use client";

import { useState } from "react";
import { Trash2, Loader2, Search, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function CleanupPage() {
  const [scanRes, setScanRes] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [keepFromDate, setKeepFromDate] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function scan() {
    setScanning(true);
    try {
      const r = await api.get<any>("/cleanup/scan-dates");
      setScanRes(r);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setScanning(false); }
  }

  async function deleteOld() {
    if (!keepFromDate) { toast.error("Choisis une date de coupure"); return; }
    if (!dryRun && !confirm("Suppression réelle — confirmer ?")) return;
    setSubmitting(true); setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/cleanup/delete-old", { keep_from_date: keepFromDate, dry_run: dryRun });
      setJobId(r.job_id);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setSubmitting(false); }
  }

  async function cleanDup() {
    if (!dryRun && !confirm("Suppression des doublons réelle — confirmer ?")) return;
    setSubmitting(true); setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/cleanup/duplicates", { dry_run: dryRun });
      setJobId(r.job_id);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Trash2 className="h-6 w-6" />}
        title="Nettoyage Notion"
        subtitle="Audit et suppression des lignes anciennes ou doublons dans la base Paiements."
      />

      <Card className="border-warning/40 bg-warning/5">
        <CardContent className="flex items-start gap-2 py-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-warning shrink-0" />
          <div>
            <strong className="text-foreground">Mode aperçu activé par défaut.</strong>{" "}
            Décoche "dry run" pour appliquer réellement.
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2 rounded-lg border border-border bg-secondary/30 p-3">
        <Label htmlFor="dry" className="text-sm normal-case tracking-normal font-medium text-foreground">
          Dry run (aperçu seulement)
        </Label>
        <Switch id="dry" checked={dryRun} onCheckedChange={setDryRun} />
      </div>

      <Tabs defaultValue="scan">
        <TabsList>
          <TabsTrigger value="scan">Scanner dates</TabsTrigger>
          <TabsTrigger value="old">Supprimer anciennes</TabsTrigger>
          <TabsTrigger value="dup">Nettoyer doublons</TabsTrigger>
        </TabsList>

        <TabsContent value="scan" className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Audit des dates</CardTitle>
              <CardDescription>Liste toutes les dates uniques avec leur compte de lignes.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={scan} disabled={scanning} variant="outline">
                {scanning ? <Loader2 className="animate-spin" /> : <Search />} Scanner
              </Button>
              {scanRes && (
                <div className="mt-3 rounded-lg bg-secondary/30 p-3 text-sm">
                  <p><strong>{scanRes.total_rows ?? "?"}</strong> ligne(s) au total</p>
                  <p className="text-xs text-muted-foreground">Date la plus récente : {scanRes.most_recent_date ?? "—"}</p>
                  {scanRes.dates_summary && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs">Détail par date</summary>
                      <pre className="mt-2 text-xs overflow-x-auto">{JSON.stringify(scanRes.dates_summary, null, 2).slice(0, 1500)}</pre>
                    </details>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="old" className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Supprimer les lignes anciennes</CardTitle>
              <CardDescription>Toutes les lignes dont la date est avant cette date seront supprimées.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label>Garder à partir de</Label>
                <Input type="date" value={keepFromDate} onChange={(e) => setKeepFromDate(e.target.value)} className="w-48" />
              </div>
              <Button onClick={deleteOld} disabled={submitting || !!jobId || !keepFromDate} variant={dryRun ? "outline" : "destructive"}>
                {submitting ? <Loader2 className="animate-spin" /> : <Trash2 />} {dryRun ? "Aperçu" : "Supprimer"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="dup" className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Nettoyer les doublons</CardTitle>
              <CardDescription>Détecte et supprime les lignes redondantes (même prof + élève + date + montant).</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={cleanDup} disabled={submitting || !!jobId} variant={dryRun ? "outline" : "destructive"}>
                {submitting ? <Loader2 className="animate-spin" /> : <Trash2 />} {dryRun ? "Aperçu" : "Nettoyer"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Nettoyage terminé 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
