"use client";

import { useEffect, useState } from "react";
import { Bell, Loader2, Send, RefreshCw, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { api, type InvoiceFolder } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type TemplateKey = "fr" | "en" | "carole";
const TABS: { key: TemplateKey; label: string; emoji: string }[] = [
  { key: "fr", label: "Français", emoji: "🇫🇷" },
  { key: "en", label: "Anglais", emoji: "🇬🇧" },
  { key: "carole", label: "Carole Tessier", emoji: "👩" },
];

export default function RemindersPage() {
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [folder, setFolder] = useState("");
  const [unpaid, setUnpaid] = useState<any>(null);
  const [auto, setAuto] = useState<{ should_send: boolean } | null>(null);
  const [templates, setTemplates] = useState<Record<TemplateKey, { subject: string; body: string }>>({
    fr: { subject: "", body: "" }, en: { subject: "", body: "" }, carole: { subject: "", body: "" },
  });
  const [loadingUnpaid, setLoadingUnpaid] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get<InvoiceFolder[]>("/invoice-folders").then((f) => {
      setFolders(f);
      if (f.length > 0) setFolder(f[0].month);
    });
    api.get<{ subject: string; body: string }>("/reminders/default-template").then((t) => {
      setTemplates((s) => ({ ...s, fr: t }));
    }).catch(() => {});
    api.get<{ should_send: boolean }>("/reminders/auto-candidates").then(setAuto).catch(() => {});
  }, []);

  async function loadUnpaid() {
    if (!folder) return;
    setLoadingUnpaid(true);
    try {
      const r = await api.get<any>(`/reminders/unpaid?folder=${encodeURIComponent(folder)}`);
      setUnpaid(r);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setLoadingUnpaid(false); }
  }

  function setTpl(key: TemplateKey, field: "subject" | "body", value: string) {
    setTemplates((t) => ({ ...t, [key]: { ...t[key], [field]: value } }));
  }

  async function send(asTest: boolean) {
    if (!folder) { toast.error("Choisis un dossier"); return; }
    setSubmitting(true); setJobId(null);
    try {
      const body = { folder, templates, selected_families: null, send_to_test: asTest };
      const r = await api.post<{ job_id: string }>(asTest ? "/reminders/test" : "/reminders/send", body);
      setJobId(r.job_id);
      toast.success(`Job lancé`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Bell className="h-6 w-6" />}
        title="Rappels de paiement"
        subtitle="3 templates : FR / EN / Carole. Pièces jointes des PDFs originaux (matching strict)."
      />

      {auto?.should_send && (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="flex items-center gap-2 py-3 text-sm text-warning">
            <AlertTriangle className="h-4 w-4" />
            <strong>C'est le 11 du mois</strong> — pense à envoyer les rappels aux familles impayées.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">1. Choisir le dossier</CardTitle>
            <select value={folder} onChange={(e) => setFolder(e.target.value)}
              className="h-10 rounded-lg border border-border bg-card px-3 text-sm">
              {folders.length === 0 ? <option>Aucun dossier</option>
                : folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
            </select>
          </div>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={loadUnpaid} disabled={loadingUnpaid || !folder}>
            {loadingUnpaid ? <Loader2 className="animate-spin" /> : <RefreshCw />} 2. Charger les impayés Notion
          </Button>
          {unpaid?.families && (
            <p className="mt-3 text-sm text-muted-foreground">
              {Object.keys(unpaid.families).length} famille(s) impayée(s)
            </p>
          )}
        </CardContent>
      </Card>

      <Tabs defaultValue="fr">
        <TabsList>{TABS.map((t) => <TabsTrigger key={t.key} value={t.key}>{t.emoji} {t.label}</TabsTrigger>)}</TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.key} value={t.key} className="space-y-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">3. Éditer le template {t.label}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Sujet</Label>
                  <Input value={templates[t.key].subject} onChange={(e) => setTpl(t.key, "subject", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Corps</Label>
                  <textarea value={templates[t.key].body} onChange={(e) => setTpl(t.key, "body", e.target.value)}
                    rows={8} className="flex w-full rounded-lg border border-border bg-card px-3 py-2 text-sm font-mono" />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={() => send(true)} disabled={submitting || !!jobId}>
          {submitting ? <Loader2 className="animate-spin" /> : <Send />} Tester
        </Button>
        <Button variant="accent" size="lg" onClick={() => send(false)} disabled={submitting || !!jobId}>
          {submitting ? <Loader2 className="animate-spin" /> : <Send />} 4. Envoyer les rappels
        </Button>
      </div>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Rappels envoyés 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
