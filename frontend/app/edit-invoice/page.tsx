"use client";

import { useEffect, useState } from "react";
import {
  Palette,
  Loader2,
  Upload,
  Download,
  Mail,
  Cloud,
  FileText,
  Trash2,
  Plus,
} from "lucide-react";
import { toast } from "sonner";

import { api, type InvoiceFolder } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface EditItem { date: string; description: string; amount: number; }
interface EditFields {
  parent_name: string;
  billing_address: string;
  parent_email: string;
  invoice_date: string; // YYYY-MM-DD
  invoice_number: string;
  currency: string;
  items: EditItem[];
  package_mode: boolean;
  package_label: string;
  total_due: number;
  pay_link_url: string;
  _origin_drive_folder_id?: string | null;
  _origin_family_subfolder?: string | null;
  _origin_pdf_filename?: string | null;
}

export default function EditInvoicePage() {
  // Source state
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [folder, setFolder] = useState("");
  const [families, setFamilies] = useState<string[]>([]);
  const [folderDownloaded, setFolderDownloaded] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [family, setFamily] = useState("");
  const [pdfs, setPdfs] = useState<string[]>([]);
  const [pdfName, setPdfName] = useState("");
  const [loading, setLoading] = useState(false);

  // Editor state
  const [fields, setFields] = useState<EditFields | null>(null);
  const [rawPdfBase64, setRawPdfBase64] = useState<string | null>(null);
  const [editedPdfBlob, setEditedPdfBlob] = useState<Blob | null>(null);
  const [editedPdfBase64, setEditedPdfBase64] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.get<InvoiceFolder[]>("/invoice-folders").then((f) => {
      setFolders(f);
      if (f.length > 0) setFolder(f[0].month);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!folder) return;
    setFamily(""); setPdfs([]); setPdfName("");
    api.get<{ downloaded: boolean; families: string[] }>(`/edit/folders/${encodeURIComponent(folder)}/families`)
      .then((r) => {
        setFamilies(r.families);
        setFolderDownloaded(r.downloaded);
      }).catch(() => { setFamilies([]); setFolderDownloaded(false); });
  }, [folder]);

  useEffect(() => {
    if (!folder || !family) return;
    setPdfName("");
    api.get<string[]>(`/edit/folders/${encodeURIComponent(folder)}/family/${encodeURIComponent(family)}/pdfs`)
      .then((r) => {
        setPdfs(r);
        if (r.length === 1) setPdfName(r[0]);
      }).catch(() => setPdfs([]));
  }, [folder, family]);

  async function downloadFolderFromDrive() {
    setDownloading(true);
    try {
      // Calling /families again triggers the download server-side
      const r = await api.get<{ downloaded: boolean; families: string[] }>(`/edit/folders/${encodeURIComponent(folder)}/families`);
      setFamilies(r.families);
      setFolderDownloaded(r.downloaded);
      toast.success(r.downloaded ? "Dossier prêt" : "Téléchargement échoué");
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setDownloading(false); }
  }

  async function loadInvoice() {
    if (!folder || !family || !pdfName) return;
    setLoading(true);
    try {
      const r = await api.post<{ raw_pdf_base64: string; fields: EditFields }>("/edit/load", {
        folder, family, pdf_filename: pdfName,
      });
      setRawPdfBase64(r.raw_pdf_base64);
      setFields(r.fields);
      setEditedPdfBlob(null);
      setEditedPdfBase64(null);
      toast.success("Facture chargée");
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setLoading(false); }
  }

  async function loadFromUpload(file: File) {
    setLoading(true);
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        const b64 = ((reader.result as string).split(",")[1]) || "";
        setRawPdfBase64(b64);
        const empty = await api.get<EditFields>("/edit/empty-fields");
        setFields(empty);
        setEditedPdfBlob(null);
        setEditedPdfBase64(null);
        toast.success("PDF uploadé, formulaire vide à remplir");
      };
      reader.readAsDataURL(file);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setLoading(false); }
  }

  async function renderPdf() {
    if (!fields) return;
    setBusy("render");
    try {
      // Auto-compute total in items mode
      const f = fields.package_mode
        ? fields
        : { ...fields, total_due: fields.items.reduce((s, it) => s + (it.amount || 0), 0) };
      const res = await fetch("/api/backend/edit/render", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "change-me" },
        body: JSON.stringify({ fields: f }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      setEditedPdfBlob(blob);
      const arrayBuf = await blob.arrayBuffer();
      const bytes = new Uint8Array(arrayBuf);
      let bin = "";
      for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
      setEditedPdfBase64(btoa(bin));
      toast.success("PDF généré");
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setBusy(null); }
  }

  function downloadEdited() {
    if (!editedPdfBlob || !fields) return;
    const safe = (fields.parent_name || "facture").replace(/\s+/g, "_");
    const date = fields.invoice_date.slice(0, 10);
    const filename = `Facture_${date}_${safe}.pdf`;
    const url = URL.createObjectURL(editedPdfBlob);
    const link = document.createElement("a");
    link.href = url; link.download = filename; link.click();
    URL.revokeObjectURL(url);
    toast.success(`${filename} téléchargé`);
  }

  async function emailEdited() {
    if (!editedPdfBase64 || !fields) return;
    setBusy("email");
    try {
      await api.post("/edit/send-email", { fields, pdf_base64: editedPdfBase64 });
      toast.success(`Envoyé à ${fields.parent_email}`);
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setBusy(null); }
  }

  async function saveToDrive() {
    if (!editedPdfBase64 || !fields?._origin_drive_folder_id || !fields._origin_family_subfolder || !fields._origin_pdf_filename) {
      toast.error("Source dossier Drive requise (charge depuis un dossier d'abord)");
      return;
    }
    setBusy("drive");
    try {
      await api.post("/edit/save-to-drive", {
        pdf_base64: editedPdfBase64,
        origin_drive_folder_id: fields._origin_drive_folder_id,
        family_subfolder: fields._origin_family_subfolder,
        pdf_filename: fields._origin_pdf_filename,
      });
      toast.success("Sauvegardé sur Drive");
    } catch (e) {
      toast.error(`${e instanceof Error ? e.message : "?"}`);
    } finally { setBusy(null); }
  }

  function setF<K extends keyof EditFields>(k: K, v: EditFields[K]) {
    if (!fields) return;
    setFields({ ...fields, [k]: v });
  }

  function updateItem(i: number, patch: Partial<EditItem>) {
    if (!fields) return;
    const items = [...fields.items];
    items[i] = { ...items[i], ...patch };
    setFields({ ...fields, items });
  }

  function addItem() {
    if (!fields) return;
    setFields({ ...fields, items: [...fields.items, { date: "", description: "", amount: 0 }] });
  }

  function deleteItem(i: number) {
    if (!fields) return;
    setFields({ ...fields, items: fields.items.filter((_, idx) => idx !== i) });
  }

  const autoTotal = fields ? fields.items.reduce((s, it) => s + (it.amount || 0), 0) : 0;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Palette className="h-6 w-6" />}
        title="Éditer une facture"
        subtitle="Charge une facture, modifie ce que tu veux, télécharge / envoie / re-stocke sur Drive."
      />

      {/* 1. SOURCE */}
      <Card>
        <CardHeader>
          <CardTitle>1️⃣ Source de la facture</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="folder">
            <TabsList>
              <TabsTrigger value="folder">📁 Dossier de factures</TabsTrigger>
              <TabsTrigger value="upload">📤 Upload PDF</TabsTrigger>
            </TabsList>

            <TabsContent value="folder" className="space-y-3">
              <div className="space-y-1.5">
                <Label>Dossier</Label>
                <select
                  value={folder}
                  onChange={(e) => setFolder(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
                >
                  {folders.length === 0 ? <option>Aucun dossier</option>
                    : folders.map((f) => <option key={f.id} value={f.month}>{f.year} / {f.month} ({f.source})</option>)}
                </select>
              </div>

              {!folderDownloaded && folder && (
                <div className="rounded-lg border border-info/30 bg-info/5 p-3 text-sm">
                  <p className="text-foreground">ℹ️ Ce dossier n'est pas en local, il faut le télécharger depuis Drive.</p>
                  <Button variant="outline" size="sm" onClick={downloadFolderFromDrive} disabled={downloading} className="mt-2">
                    {downloading ? <Loader2 className="animate-spin" /> : <Download />} Télécharger le dossier depuis Drive
                  </Button>
                </div>
              )}

              {folderDownloaded && families.length > 0 && (
                <>
                  <div className="space-y-1.5">
                    <Label>Famille</Label>
                    <select value={family} onChange={(e) => setFamily(e.target.value)}
                      className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                      <option value="">— Choisir —</option>
                      {families.map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                  {family && pdfs.length > 0 && (
                    <div className="space-y-1.5">
                      <Label>PDF</Label>
                      <select value={pdfName} onChange={(e) => setPdfName(e.target.value)}
                        className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                        <option value="">— Choisir —</option>
                        {pdfs.map((p) => <option key={p} value={p}>{p}</option>)}
                      </select>
                    </div>
                  )}
                  <Button variant="accent" onClick={loadInvoice} disabled={loading || !pdfName}>
                    {loading ? <Loader2 className="animate-spin" /> : <FileText />} Charger cette facture
                  </Button>
                </>
              )}
            </TabsContent>

            <TabsContent value="upload" className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Glisse un PDF de facture pour l'éditer (le formulaire sera vide, à remplir).
              </p>
              <Input type="file" accept="application/pdf" onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void loadFromUpload(file);
              }} />
            </TabsContent>
          </Tabs>

          {!fields && (
            <div className="mt-4 rounded-lg border border-info/30 bg-info/5 p-3 text-sm">
              👆 Charge d'abord une facture via les onglets ci-dessus.
            </div>
          )}
        </CardContent>
      </Card>

      {/* 2. EDITION */}
      {fields && (
        <Card>
          <CardHeader>
            <CardTitle>2️⃣ Édition des champs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>Nom du parent / famille</Label>
              <Input value={fields.parent_name} onChange={(e) => setF("parent_name", e.target.value)} />
            </div>

            <div className="space-y-1.5">
              <Label>Adresse 'Facturer à' (multi-ligne — vide = utiliser nom du parent)</Label>
              <textarea
                value={fields.billing_address}
                onChange={(e) => setF("billing_address", e.target.value)}
                rows={4}
                placeholder="Ex : OCTOPUS SARL&#10;C/o CATS BUSINESS CENTER&#10;28 bd Princesse Charlotte&#10;98 000 MONACO"
                className="flex w-full rounded-lg border border-border bg-card px-3 py-2 text-sm font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <Label>Email du destinataire</Label>
              <Input type="email" value={fields.parent_email} onChange={(e) => setF("parent_email", e.target.value)} />
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label>Date de facture</Label>
                <Input type="date" value={fields.invoice_date} onChange={(e) => setF("invoice_date", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>N° de facture (vide = auto)</Label>
                <Input value={fields.invoice_number} onChange={(e) => setF("invoice_number", e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label>Devise</Label>
                <select value={fields.currency} onChange={(e) => setF("currency", e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm">
                  <option>EUR</option><option>CHF</option><option>AED</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
              <Label className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
                📦 Format Package (1 ligne, style OCTOPUS Carole)
              </Label>
              <Switch checked={fields.package_mode} onCheckedChange={(c) => setF("package_mode", c)} />
            </div>

            {fields.package_mode ? (
              <>
                <div className="space-y-1.5">
                  <Label>Libellé du Package</Label>
                  <Input value={fields.package_label} onChange={(e) => setF("package_label", e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Total dû</Label>
                  <Input type="number" step="0.01" value={fields.total_due}
                    onChange={(e) => setF("total_due", parseFloat(e.target.value) || 0)} />
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="normal-case tracking-normal text-sm">📋 Lignes de la facture</Label>
                  <Button variant="outline" size="sm" onClick={addItem}><Plus /> Ajouter</Button>
                </div>
                <div className="space-y-2">
                  {fields.items.map((it, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2">
                      <Input placeholder="JJ.MM.AAAA" value={it.date} onChange={(e) => updateItem(i, { date: e.target.value })} className="col-span-2" />
                      <Input placeholder="Description" value={it.description} onChange={(e) => updateItem(i, { description: e.target.value })} className="col-span-7" />
                      <Input type="number" step="0.01" value={it.amount} onChange={(e) => updateItem(i, { amount: parseFloat(e.target.value) || 0 })} className="col-span-2" />
                      <Button variant="ghost" size="icon" onClick={() => deleteItem(i)} className="col-span-1">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  ))}
                </div>
                <div className="text-right text-sm">
                  Total auto : <span className="font-semibold">{autoTotal.toFixed(2)} {fields.currency}</span>
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <Label>Lien Stripe (bouton "Cliquez ici pour payer")</Label>
              <Input value={fields.pay_link_url} onChange={(e) => setF("pay_link_url", e.target.value)} placeholder="https://buy.stripe.com/..." />
            </div>

            {rawPdfBase64 && (
              <details>
                <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
                  👁 Aperçu du PDF original
                </summary>
                <iframe src={`data:application/pdf;base64,${rawPdfBase64}`} className="mt-2 w-full h-96 rounded border border-border" />
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {/* 3. OUTPUT */}
      {fields && (
        <Card>
          <CardHeader>
            <CardTitle>3️⃣ Générer & Exporter</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button variant="accent" size="lg" onClick={renderPdf} disabled={busy !== null} className="w-full">
              {busy === "render" ? <Loader2 className="animate-spin" /> : <FileText />} Générer le PDF édité
            </Button>

            {editedPdfBlob && (
              <>
                <iframe src={URL.createObjectURL(editedPdfBlob)} className="w-full h-[600px] rounded border border-border" />
                <div className="grid gap-2 sm:grid-cols-3">
                  <Button variant="outline" onClick={downloadEdited} disabled={busy !== null}>
                    <Download /> Télécharger
                  </Button>
                  <Button variant="outline" onClick={emailEdited} disabled={busy !== null || !fields.parent_email}>
                    {busy === "email" ? <Loader2 className="animate-spin" /> : <Mail />} Envoyer par email
                  </Button>
                  <Button variant="outline" onClick={saveToDrive} disabled={busy !== null || !fields._origin_drive_folder_id}>
                    {busy === "drive" ? <Loader2 className="animate-spin" /> : <Cloud />} Écraser sur Drive
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
