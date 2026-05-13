"use client";

import { useEffect, useState } from "react";
import { Upload, Loader2, Search, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { api, type InvoiceFolder, type ExtractedFamily } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function UpdateNotionPage() {
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [folder, setFolder] = useState("");
  const [noSplit, setNoSplit] = useState(true);
  const [families, setFamilies] = useState<ExtractedFamily[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [scanResult, setScanResult] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get<InvoiceFolder[]>("/invoice-folders").then((f) => {
      setFolders(f);
      if (f.length > 0) setFolder(f[0].month);
    });
    api.get<ExtractedFamily[]>("/payment-links/families").then(setFamilies).catch(() => {});
  }, []);

  async function launchAll() {
    setSubmitting(true); setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/update-notion/all", { no_split: noSplit });
      setJobId(r.job_id);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setSubmitting(false); }
  }

  async function launchSelection() {
    if (selected.size === 0) { toast.error("Sélectionne au moins une famille"); return; }
    setSubmitting(true); setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/update-notion/selection", {
        invoice_folder_path: folder,
        selected_family_ids: Array.from(selected),
        selected_teachers: null,
        no_split: noSplit,
      });
      setJobId(r.job_id);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setSubmitting(false); }
  }

  async function scanCompare() {
    if (!folder) return;
    setScanning(true);
    try {
      const r = await api.get<any>(`/update-notion/scan-compare?folder_path=${encodeURIComponent(folder)}`);
      setScanResult(r);
      toast.success(`${r?.missing?.length ?? 0} ligne(s) manquante(s) détectée(s)`);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setScanning(false); }
  }

  async function addMissing() {
    if (!scanResult?.missing) return;
    setSubmitting(true); setJobId(null);
    try {
      const r = await api.post<{ job_id: string }>("/update-notion/add-missing", {
        missing_rows: scanResult.missing,
      });
      setJobId(r.job_id);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Upload className="h-6 w-6" />}
        title="Ajouter lignes Notion"
        subtitle="Pousse les leçons extraites vers la base 'Paiements – Base Centrale'. additional_amounts géré (n-2)."
      />

      <Card>
        <CardContent className="flex items-center justify-between gap-3 pt-6">
          <span className="text-sm font-medium">Mode NO-SPLIT</span>
          <Switch checked={noSplit} onCheckedChange={setNoSplit} />
        </CardContent>
      </Card>

      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">Ajout massif</TabsTrigger>
          <TabsTrigger value="selection">Par sélection</TabsTrigger>
          <TabsTrigger value="scan">Scan & comparer</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Ajout massif</CardTitle>
              <CardDescription>Ajoute toutes les familles de l'extraction en cours dans Notion.</CardDescription>
            </CardHeader>
          </Card>
          <div className="flex justify-end">
            <Button variant="accent" size="lg" onClick={launchAll} disabled={submitting || !!jobId}>
              {submitting ? <Loader2 className="animate-spin" /> : <Upload />} Ajouter toutes
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="selection" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sélectionner les familles</CardTitle>
            </CardHeader>
            <CardContent>
              <select value={folder} onChange={(e) => setFolder(e.target.value)}
                className="mb-3 h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                {folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
              </select>
              <div className="overflow-hidden rounded-lg border border-border max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {families.map((f) => (
                      <tr key={f.family_id} className="border-t border-border">
                        <td className="p-2 w-10">
                          <Checkbox checked={selected.has(f.family_id)} onCheckedChange={(c) => {
                            const next = new Set(selected);
                            if (c) next.add(f.family_id); else next.delete(f.family_id);
                            setSelected(next);
                          }} />
                        </td>
                        <td className="p-2 font-medium">{f.parent_name}</td>
                        <td className="p-2 text-right tabular-nums text-muted-foreground">{f.lessons}l</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          <div className="flex justify-end">
            <Button variant="accent" size="lg" onClick={launchSelection} disabled={submitting || !!jobId || selected.size === 0}>
              {submitting ? <Loader2 className="animate-spin" /> : <Upload />} Ajouter ({selected.size})
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="scan" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Scan & comparer</CardTitle>
              <CardDescription>Compare les PDFs Drive aux lignes Notion existantes pour ce dossier.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <select value={folder} onChange={(e) => setFolder(e.target.value)}
                className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                {folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
              </select>
              <Button variant="outline" onClick={scanCompare} disabled={scanning || !folder}>
                {scanning ? <Loader2 className="animate-spin" /> : <Search />} Scanner
              </Button>
              {scanResult && (
                <div className="rounded-lg bg-secondary/30 p-3 text-sm">
                  <p><strong>{scanResult.missing?.length ?? 0}</strong> ligne(s) manquante(s) à ajouter</p>
                  {scanResult.missing?.length > 0 && (
                    <ul className="mt-2 max-h-40 overflow-y-auto text-xs space-y-0.5">
                      {scanResult.missing.slice(0, 20).map((m: any, i: number) => (
                        <li key={i} className="font-mono">{m.parent_name || JSON.stringify(m).slice(0, 80)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
          {scanResult?.missing?.length > 0 && (
            <div className="flex justify-end">
              <Button variant="accent" size="lg" onClick={addMissing} disabled={submitting || !!jobId}>
                {submitting ? <Loader2 className="animate-spin" /> : <Plus />} Ajouter les manquantes
              </Button>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Notion mis à jour 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
