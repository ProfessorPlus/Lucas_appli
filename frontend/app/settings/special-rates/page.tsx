"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Loader2, Tag } from "lucide-react";
import { toast } from "sonner";

import { api, type SpecialRate, type Teacher } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/EmptyState";

export default function SpecialRatesPage() {
  const [list, setList] = useState<SpecialRate[] | null>(null);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [creating, setCreating] = useState(false);

  // form
  const [teacher, setTeacher] = useState("");
  const [parent, setParent] = useState("");
  const [student, setStudent] = useState("");
  const [rate, setRate] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [submitting, setSubmitting] = useState(false);

  async function reload() {
    try {
      const [rates, t] = await Promise.all([
        api.get<SpecialRate[]>("/settings/special-rates"),
        api.get<Teacher[]>("/settings/teachers"),
      ]);
      setList(rates);
      setTeachers(t);
    } catch {
      toast.error("Impossible de charger les tarifs spéciaux");
    }
  }
  useEffect(() => { void reload(); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!teacher || !parent || !rate) return;
    setSubmitting(true);
    try {
      await api.post("/settings/special-rates", {
        teacher,
        parent: parent.trim(),
        student: student.trim() || undefined,
        pay_rate: parseFloat(rate),
        currency,
      });
      toast.success("Tarif spécial ajouté");
      setTeacher(""); setParent(""); setStudent(""); setRate(""); setCurrency("EUR");
      setCreating(false);
      await reload();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string, label: string) {
    if (!confirm(`Supprimer le tarif "${label}" ?`)) return;
    try {
      await api.delete(`/settings/special-rates/${id}`);
      toast.success("Tarif supprimé");
      await reload();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight">Tarifs spéciaux</h2>
          <p className="text-sm text-muted-foreground">
            Exceptions par couple prof/famille — par défaut on utilise le taux du prof dans secrets.yaml.
          </p>
        </div>
        <Button variant="accent" onClick={() => setCreating(!creating)}>
          <Plus /> Ajouter
        </Button>
      </div>

      {creating && (
        <Card className="border-accent/30">
          <CardHeader>
            <CardTitle>Nouveau tarif spécial</CardTitle>
            <CardDescription>Override du taux du prof pour une famille (et optionnellement un élève).</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="sr-teacher">Professeur</Label>
                <select
                  id="sr-teacher"
                  value={teacher}
                  onChange={(e) => setTeacher(e.target.value)}
                  className="flex h-10 w-full rounded-lg border border-border bg-card px-3 text-sm"
                  required
                >
                  <option value="">— Choisir —</option>
                  {teachers.map((t) => (
                    <option key={t.name} value={t.name}>{t.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sr-parent">Parent (famille)</Label>
                <Input id="sr-parent" value={parent} onChange={(e) => setParent(e.target.value)} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sr-student">Élève (optionnel)</Label>
                <Input id="sr-student" value={student} onChange={(e) => setStudent(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sr-rate">Tarif horaire</Label>
                <div className="flex gap-2">
                  <Input
                    id="sr-rate"
                    type="number"
                    step="0.01"
                    value={rate}
                    onChange={(e) => setRate(e.target.value)}
                    required
                  />
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="flex h-10 rounded-lg border border-border bg-card px-3 text-sm"
                  >
                    <option>EUR</option>
                    <option>CHF</option>
                    <option>AED</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2 sm:col-span-2">
                <Button type="button" variant="ghost" onClick={() => setCreating(false)}>Annuler</Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? <Loader2 className="animate-spin" /> : <Plus />} Ajouter
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {list === null ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </CardContent>
        </Card>
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Tag className="h-6 w-6" />}
          title="Aucun tarif spécial"
          description="Tous les profs sont payés à leur taux par défaut."
        />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="p-3 text-left font-semibold">Professeur</th>
                <th className="p-3 text-left font-semibold">Parent</th>
                <th className="p-3 text-left font-semibold">Élève</th>
                <th className="p-3 text-right font-semibold">Tarif/h</th>
                <th className="p-3 text-right font-semibold"></th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="p-3 font-medium">{r.teacher}</td>
                  <td className="p-3">{r.parent}</td>
                  <td className="p-3 text-muted-foreground">{r.student || "—"}</td>
                  <td className="p-3 text-right tabular-nums font-semibold">
                    {r.pay_rate.toFixed(2)}{" "}
                    <Badge variant="secondary" className="text-[10px]">{r.currency}</Badge>
                  </td>
                  <td className="p-3 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(r.id, `${r.teacher} → ${r.parent}`)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
