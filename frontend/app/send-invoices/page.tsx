"use client";

import { useEffect, useState } from "react";
import { Mail, Loader2, Send, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { api, type InvoiceFolder } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { JobRunner } from "@/components/shared/JobRunner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

type TemplateKey = "fr" | "en" | "carole" | "multi";
const TABS: { key: TemplateKey; label: string; emoji: string }[] = [
  { key: "fr", label: "Français", emoji: "🇫🇷" },
  { key: "en", label: "Anglais", emoji: "🇬🇧" },
  { key: "carole", label: "Carole Tessier", emoji: "👩" },
  { key: "multi", label: "Multi-mois", emoji: "📌" },
];

export default function SendInvoicesPage() {
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [folder, setFolder] = useState("");
  const [preview, setPreview] = useState<Record<string, string[]>>({});
  const [templates, setTemplates] = useState<Record<TemplateKey, { subject: string; body: string }>>({
    fr: { subject: "", body: "" }, en: { subject: "", body: "" },
    carole: { subject: "", body: "" }, multi: { subject: "", body: "" },
  });
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get<InvoiceFolder[]>("/invoice-folders").then((f) => {
      setFolders(f);
      if (f.length > 0) setFolder(f[0].month);
    });
    // Load default templates
    api.get<Record<TemplateKey, { subject: string; body: string }>>(
      "/send/default-templates?month=Avril&year=2026",
    ).then(setTemplates).catch(() => {});
  }, []);

  useEffect(() => {
    if (!folder) return;
    api.get<Record<string, string[]>>(`/send/preview?folder=${encodeURIComponent(folder)}`)
      .then(setPreview).catch(() => {});
  }, [folder]);

  function setTpl(key: TemplateKey, field: "subject" | "body", value: string) {
    setTemplates((t) => ({ ...t, [key]: { ...t[key], [field]: value } }));
  }

  async function send(asTest: boolean) {
    if (!folder) { toast.error("Choisis un dossier"); return; }
    setSubmitting(true);
    setJobId(null);
    try {
      const body = {
        folder, templates,
        selected_families: null, send_to_test: asTest,
      };
      const r = await api.post<{ job_id: string }>(asTest ? "/send/test" : "/send/invoices", body);
      setJobId(r.job_id);
      toast.success(`Job lancé — ${r.job_id.slice(0, 8)}`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Mail className="h-6 w-6" />}
        title="Envoi des factures"
        subtitle="4 templates : Français · Anglais · Carole Tessier · Multi-mois (priorité dans cet ordre inverse)."
      />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Dossier de factures</CardTitle>
            </div>
            <select value={folder} onChange={(e) => setFolder(e.target.value)}
              className="h-10 rounded-lg border border-border bg-card px-3 text-sm">
              {folders.length === 0 ? <option>Aucun dossier</option>
                : folders.map((f) => <option key={f.id} value={f.month}>{f.month}</option>)}
            </select>
          </div>
        </CardHeader>
      </Card>

      <Tabs defaultValue="fr">
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key}>
              {t.emoji} {t.label} {preview[t.key]?.length ? <Badge variant="secondary" className="text-[10px] ml-1">{preview[t.key].length}</Badge> : null}
            </TabsTrigger>
          ))}
        </TabsList>

        {TABS.map((t) => (
          <TabsContent key={t.key} value={t.key} className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Template {t.emoji} {t.label}</CardTitle>
                <CardDescription>
                  {preview[t.key]?.length ? (
                    <span>
                      {preview[t.key].length} famille(s) recevront ce template :{" "}
                      <span className="text-foreground">{preview[t.key].slice(0, 5).join(", ")}</span>
                      {preview[t.key].length > 5 && ` … +${preview[t.key].length - 5}`}
                    </span>
                  ) : "Aucune famille pour ce template avec ce dossier."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1.5">
                  <Label>Sujet</Label>
                  <Input value={templates[t.key].subject} onChange={(e) => setTpl(t.key, "subject", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Corps</Label>
                  <textarea
                    value={templates[t.key].body}
                    onChange={(e) => setTpl(t.key, "body", e.target.value)}
                    rows={8}
                    className="flex w-full rounded-lg border border-border bg-card px-3 py-2 text-sm font-mono"
                  />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" onClick={() => send(true)} disabled={submitting || !!jobId}>
          {submitting ? <Loader2 className="animate-spin" /> : <Send />} Tester (envoi à soi)
        </Button>
        <Button variant="accent" size="lg" onClick={() => send(false)} disabled={submitting || !!jobId}>
          {submitting ? <Loader2 className="animate-spin" /> : <Send />} Envoyer aux familles
        </Button>
      </div>

      {jobId && (
        <Card>
          <CardHeader><CardTitle>Job en cours</CardTitle></CardHeader>
          <CardContent>
            <JobRunner jobId={jobId} onDone={() => toast.success("Envoi terminé 🎉")} onError={(e) => toast.error(e)} onCancel={() => setJobId(null)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
