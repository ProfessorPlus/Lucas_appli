"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, XCircle, Database, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";

import { api, type DriveTestResult, type DriveWriteTestResult } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DriveSettingsPage() {
  const [readT, setReadT] = useState<DriveTestResult | null>(null);
  const [writeT, setWriteT] = useState<DriveWriteTestResult | null>(null);
  const [reading, setReading] = useState(false);
  const [writing, setWriting] = useState(false);

  async function probeRead() {
    setReading(true);
    try {
      setReadT(await api.get<DriveTestResult>("/settings/drive/test"));
    } catch (e) {
      toast.error(`Test lecture Drive échoué : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setReading(false);
    }
  }
  async function probeWrite() {
    setWriting(true);
    try {
      const r = await api.post<DriveWriteTestResult>("/settings/drive/write-test", {});
      setWriteT(r);
      if (r.ok) toast.success("Test écriture Drive OK");
      else toast.error(`Test écriture échoué : ${r.error}`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setWriting(false);
    }
  }

  useEffect(() => { void probeRead(); }, []);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Google Drive</h2>
        <p className="text-sm text-muted-foreground">
          Test de la connexion au dossier <code className="text-xs bg-secondary px-1.5 py-0.5 rounded">Professor_Plus_Data</code>.
          C'est ici que sont stockés les YAML de config + les PDFs factures.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Database className="h-4 w-4 text-accent" />
                Test de lecture
              </CardTitle>
              <Button variant="ghost" size="icon" onClick={probeRead} disabled={reading} aria-label="Refresh">
                <RefreshCw className={reading ? "animate-spin" : ""} />
              </Button>
            </div>
            <CardDescription>Liste les fichiers dans le dossier <code>config/</code> sur Drive.</CardDescription>
          </CardHeader>
          <CardContent>
            {readT === null ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Test en cours…
              </p>
            ) : readT.ok ? (
              <div className="space-y-2 text-sm">
                <p className="flex items-center gap-2 text-success font-medium">
                  <CheckCircle2 className="h-4 w-4" /> Connexion OK
                </p>
                <p className="text-xs text-muted-foreground font-mono">
                  Root: {readT.root_id?.slice(0, 16)}…<br />
                  Config: {readT.config_folder_id?.slice(0, 16)}…
                </p>
                <details>
                  <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                    {readT.files?.length} fichier(s)
                  </summary>
                  <ul className="mt-2 space-y-1 text-xs">
                    {readT.files?.map((f) => (
                      <li key={f.id} className="font-mono">
                        {f.name}
                        <span className="ml-2 text-muted-foreground">
                          ({f.modifiedTime?.slice(0, 10)})
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              </div>
            ) : (
              <p className="flex items-center gap-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" /> {readT.error}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-4 w-4 text-accent" />
              Test d'écriture
            </CardTitle>
            <CardDescription>
              Update un fichier de test (contenu identique). Le service account ne peut pas <em>créer</em> de nouveaux fichiers — c'est normal.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={probeWrite} disabled={writing} variant="outline" className="mb-3">
              {writing ? <Loader2 className="animate-spin" /> : <Upload />} Lancer le test
            </Button>
            {writeT?.ok && (
              <div className="space-y-1 text-sm">
                <p className="flex items-center gap-2 text-success font-medium">
                  <CheckCircle2 className="h-4 w-4" /> Test OK
                </p>
                <p className="text-xs text-muted-foreground">
                  Target: <code className="font-mono">{writeT.test_target}</code><br />
                  Modified: {writeT.new_modified_time}
                </p>
              </div>
            )}
            {writeT?.ok === false && (
              <p className="flex items-center gap-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" /> {writeT.error}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
