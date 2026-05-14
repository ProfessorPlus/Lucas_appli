"use client";

import { useEffect, useState } from "react";
import { FileText, Loader2, Sparkles, RefreshCw, Download } from "lucide-react";
import { toast } from "sonner";

import { api, type InvoiceFolder, type UnpaidN2Response } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function InvoicesPage() {
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [targetFolder, setTargetFolder] = useState("");
  const [forceNew, setForceNew] = useState(false);
  const [includeN2, setIncludeN2] = useState(false);
  const [n2Year, setN2Year] = useState(new Date().getFullYear());
  const [n2Month, setN2Month] = useState(((new Date().getMonth() + 12 - 2) % 12) + 1);
  const [unpaid, setUnpaid] = useState<UnpaidN2Response | null>(null);
  const [previousMonthLabel, setPreviousMonthLabel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  useEffect(() => {
    api.get<InvoiceFolder[]>("/invoice-folders").then((f) => {
      setFolders(f);
      if (f.length > 0) setTargetFolder(f[0].month);
    }).catch(() => {});
  }, []);

  async function detectUnpaid() {
    try {
      const r = await api.get<UnpaidN2Response>(`/invoices/unpaid-detect?year=${n2Year}&month=${n2Month}`);
      setUnpaid(r);
      setPreviousMonthLabel(r.month_label || `${n2Month}/${n2Year}`);
      toast.success(`${r.total_rows ?? 0} ligne(s) impayées détectées`);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    }
  }

  async function launch() {
    if (submitting) return;
    setSubmitting(true);
    setJobId(null);
    try {
      const body = {
        target_folder_path: forceNew ? null : (targetFolder || null),
        force_new_folder: forceNew,
        previous_unpaid_data: includeN2 && unpaid?.families ? unpaid.families : null,
        previous_month_label: includeN2 ? previousMonthLabel : null,
      };
      const r = await api.post<{ job_id: string }>("/invoices/generate", body);
      setJobId(r.job_id);
      toast.success(`Job lancé — ${r.job_id.slice(0, 8)}`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<FileText className="h-6 w-6" />}
        title="Génération des factures"
        subtitle="Génère les PDFs facture par famille. Pour éditer une facture déjà existante, utilise plutôt 'Éditer une facture'."
      />

      <Tabs defaultValue="generate">
        <TabsList>
          <TabsTrigger value="generate">Générer</TabsTrigger>
          <TabsTrigger value="regenerate">Régénérer dossier</TabsTrigger>
        </TabsList>

        <TabsContent value="generate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Dossier cible</CardTitle>
              <CardDescription>Crée un nouveau dossier daté ou réutilise un existant.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <Label htmlFor="new" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
                  Forcer un nouveau dossier
                </Label>
                <Switch id="new" checked={forceNew} onCheckedChange={setForceNew} />
              </div>
              {!forceNew && (
                <div className="space-y-1.5">
                  <Label htmlFor="folder">Dossier à utiliser</Label>
                  <select
                    id="folder"
                    value={targetFolder}
                    onChange={(e) => setTargetFolder(e.target.value)}
                    className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
                  >
                    {folders.length === 0 ? <option>Aucun dossier — coche "Forcer nouveau"</option>
                      : folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
                  </select>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Inclure impayés n-2</CardTitle>
              <CardDescription>Section "Rappel" dans la facture avec cumul des leçons impayées.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-3">
                <Switch checked={includeN2} onCheckedChange={setIncludeN2} />
                <span className="text-sm">Activer</span>
              </div>
              {includeN2 && (
                <div className="space-y-3 rounded-lg border border-border p-3">
                  <div className="flex items-end gap-2">
                    <div className="space-y-1.5">
                      <Label>Année</Label>
                      <Input type="number" value={n2Year} onChange={(e) => setN2Year(parseInt(e.target.value, 10))} className="w-24" />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Mois</Label>
                      <Input type="number" min={1} max={12} value={n2Month} onChange={(e) => setN2Month(parseInt(e.target.value, 10))} className="w-20" />
                    </div>
                    <Button variant="outline" size="sm" onClick={detectUnpaid}><RefreshCw /> Détecter</Button>
                  </div>
                  {unpaid && (
                    <p className="text-sm text-muted-foreground">
                      {Object.keys(unpaid.families).length} famille(s) — {unpaid.total_rows} ligne(s) impayée(s) en {unpaid.month_label}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button variant="accent" size="lg" onClick={launch} disabled={submitting || !!jobId}>
              {submitting ? <Loader2 className="animate-spin" /> : <Sparkles />} Générer les factures
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="regenerate" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Régénérer dans un dossier existant</CardTitle>
              <CardDescription>
                Les anciens PDFs de la famille sont supprimés AVANT régénération (évite les doublons).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-1.5">
                <Label>Dossier cible</Label>
                <select value={targetFolder} onChange={(e) => setTargetFolder(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                  {folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
                </select>
              </div>
            </CardContent>
          </Card>
          <div className="flex justify-end">
            <Button variant="accent" size="lg" onClick={() => { setForceNew(false); launch(); }} disabled={submitting || !!jobId}>
              {submitting ? <Loader2 className="animate-spin" /> : <RefreshCw />} Régénérer
            </Button>
          </div>
        </TabsContent>
      </Tabs>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Factures générées 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}

      {folders.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Dossiers existants</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {folders.slice(0, 10).map((f) => (
                <li key={f.id} className="flex items-center justify-between border-b border-border py-1.5">
                  <span className="font-mono text-xs">{f.month}</span>
                  <span className="text-xs text-muted-foreground">{f.source}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
