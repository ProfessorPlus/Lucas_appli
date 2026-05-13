"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Loader2, Wallet } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/shared/EmptyState";

export default function FamiliesEurPage() {
  const [list, setList] = useState<string[] | null>(null);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);

  async function reload() {
    try {
      setList(await api.get<string[]>("/settings/families-eur"));
    } catch {
      toast.error("Impossible de charger la liste");
    }
  }
  useEffect(() => {
    void reload();
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setAdding(true);
    try {
      await api.post<string[]>("/settings/families-eur", { name: newName.trim() });
      toast.success(`"${newName.trim()}" ajoutée`);
      setNewName("");
      await reload();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setAdding(false);
    }
  }

  async function remove(name: string) {
    if (!confirm(`Retirer "${name}" de la liste EUR ?`)) return;
    try {
      await api.delete(`/settings/families-eur/${encodeURIComponent(name)}`);
      toast.success(`"${name}" retirée`);
      await reload();
    } catch (e) {
      toast.error(`Échec : ${e instanceof Error ? e.message : "?"}`);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Familles facturées en EUR</h2>
        <p className="text-sm text-muted-foreground">
          Familles TutorBird qui doivent recevoir leurs factures en euros (au lieu de CHF par défaut).
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={add} className="flex items-end gap-2">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="fe-name">Ajouter une famille</Label>
              <Input
                id="fe-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Ex: Calabresi Aurélie"
              />
            </div>
            <Button type="submit" disabled={adding || !newName.trim()} variant="accent">
              {adding ? <Loader2 className="animate-spin" /> : <Plus />} Ajouter
            </Button>
          </form>
        </CardContent>
      </Card>

      {list === null ? (
        <Card>
          <CardContent className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </CardContent>
        </Card>
      ) : list.length === 0 ? (
        <EmptyState
          icon={<Wallet className="h-6 w-6" />}
          title="Aucune famille EUR"
          description="Toutes les familles seront facturées en CHF par défaut."
        />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="p-3 text-left font-semibold">Nom du parent</th>
                <th className="p-3 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody>
              {list.map((name) => (
                <tr key={name} className="border-t border-border">
                  <td className="p-3 font-medium">{name}</td>
                  <td className="p-3 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(name)}
                      aria-label={`Retirer ${name}`}
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
