"use client";

import { useEffect, useState } from "react";
import { Loader2, Save, Send, CheckCircle2, Mail } from "lucide-react";
import { toast } from "sonner";

import { api, type EmailConfig } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function EmailSettingsPage() {
  const [cfg, setCfg] = useState<EmailConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  async function reload() {
    try {
      const c = await api.get<EmailConfig>("/settings/email");
      setCfg(c);
      setEmail(c.email);
    } catch {
      toast.error("Impossible de charger la config Gmail");
    }
  }
  useEffect(() => { void reload(); }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/settings/email", {
        email,
        app_password: password || undefined, // only send if changed
      });
      toast.success("Configuration Gmail sauvegardée");
      setPassword("");
      await reload();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    try {
      const r = await api.post<{ sent_to: string }>("/settings/email/test", {});
      toast.success(`Test envoyé à ${r.sent_to}`);
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Configuration Gmail</h2>
        <p className="text-sm text-muted-foreground">
          Utilisée pour envoyer les factures et rappels aux familles. Nécessite un mot de passe d'application Google.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-accent" />
            SMTP Gmail
          </CardTitle>
          <CardDescription>
            Génère un mot de passe d'application sur{" "}
            <a
              className="underline text-accent hover:text-accent/80"
              href="https://myaccount.google.com/apppasswords"
              target="_blank"
              rel="noreferrer"
            >
              myaccount.google.com/apppasswords
            </a>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="g-email">Adresse Gmail</Label>
              <Input
                id="g-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="professorplus.soutienscolaire@gmail.com"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="g-pass">Mot de passe d'application</Label>
              <Input
                id="g-pass"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={cfg?.app_password_set ? `Actuel : ${cfg.app_password_preview}` : "16 caractères Google App Password"}
              />
              {cfg?.app_password_set && (
                <p className="flex items-center gap-1 text-xs text-success">
                  <CheckCircle2 className="h-3 w-3" /> Mot de passe configuré (laisse vide pour ne pas changer)
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={test} disabled={testing || !cfg?.app_password_set}>
                {testing ? <Loader2 className="animate-spin" /> : <Send />} Tester l'envoi
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? <Loader2 className="animate-spin" /> : <Save />} Enregistrer
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
