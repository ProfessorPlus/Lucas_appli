"use client";

import { useEffect, useState } from "react";
import { Users, Loader2, Download, Package, FileText } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { FXRateBadge } from "@/components/shared/FXRateBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface PayrollTeacher {
  name: string;
  nb_lessons: number;
  total_hours: number;
  eur: number;
  chf_as_eur: number;
  total_eur: number;
  details: any[];
}

interface PayrollSummary {
  teachers: PayrollTeacher[];
  grand_total: number;
  total_lessons: number;
  fx: { source?: string; factor?: number };
}

export default function PayrollPage() {
  const [summary, setSummary] = useState<PayrollSummary | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    api.get<PayrollSummary>("/payroll/summary").then(setSummary).catch((e) =>
      toast.error(`${e instanceof Error ? e.message : "?"}`)
    );
  }, []);

  async function dl(url: string, filename: string, key: string) {
    setDownloading(key);
    try {
      const res = await fetch(`/api/backend${url}`, {
        headers: { "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || "change-me" },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success(`${filename} téléchargé`);
    } catch (e) { toast.error(`${e instanceof Error ? e.message : "?"}`); }
    finally { setDownloading(null); }
  }

  const activeTeachers = summary?.teachers.filter((t) => t.nb_lessons > 0) ?? [];
  const totalEurOnly = activeTeachers.reduce((s, t) => s + t.eur, 0);
  const totalChfAsEur = activeTeachers.reduce((s, t) => s + t.chf_as_eur, 0);

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Users className="h-6 w-6" />}
        title="Récap paie professeurs"
        subtitle={summary ? `${activeTeachers.length} prof(s) actif(s) · ${summary.total_lessons} leçons` : "Chargement…"}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <StatsCard label="Total à verser" value={summary ? `${summary.grand_total.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €` : "—"} icon={<Package className="h-5 w-5" />} tone="emerald" delay={0} />
        <StatsCard label="Profs EUR (direct)" value={summary ? `${totalEurOnly.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €` : "—"} tone="primary" delay={0.05} />
        <StatsCard label="Profs CHF→EUR" value={summary ? `${totalChfAsEur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €` : "—"} tone="amber" delay={0.1} />
      </div>

      {summary?.fx?.factor && (
        <FXRateBadge pair="CHF→EUR" rate={summary.fx.factor} source={summary.fx.source?.toLowerCase().includes("frankfurter") ? "frankfurter" : "hardcoded"} />
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => dl("/payroll/zip", "recap_profs.zip", "zip")} disabled={!!downloading}>
          {downloading === "zip" ? <Loader2 className="animate-spin" /> : <Package />} ZIP (1 PDF/prof)
        </Button>
        <Button variant="outline" onClick={() => dl("/payroll/combined-pdf", "recap_profs_combined.pdf", "comb")} disabled={!!downloading}>
          {downloading === "comb" ? <Loader2 className="animate-spin" /> : <FileText />} PDF combiné
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Détail par professeur</CardTitle>
          <CardDescription>Triés par total décroissant.</CardDescription>
        </CardHeader>
        <CardContent>
          {summary === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
            </p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="p-3 text-left font-semibold">Professeur</th>
                    <th className="p-3 text-right font-semibold">Leçons</th>
                    <th className="p-3 text-right font-semibold">Heures</th>
                    <th className="p-3 text-right font-semibold">EUR direct</th>
                    <th className="p-3 text-right font-semibold">CHF→EUR</th>
                    <th className="p-3 text-right font-semibold">Total €</th>
                    <th className="p-3 text-right font-semibold">PDF</th>
                  </tr>
                </thead>
                <tbody>
                  {activeTeachers
                    .sort((a, b) => b.total_eur - a.total_eur)
                    .map((t) => (
                      <tr key={t.name} className="border-t border-border">
                        <td className="p-3 font-medium">{t.name}</td>
                        <td className="p-3 text-right tabular-nums">{t.nb_lessons}</td>
                        <td className="p-3 text-right tabular-nums">{t.total_hours.toFixed(1)} h</td>
                        <td className="p-3 text-right tabular-nums text-muted-foreground">
                          {t.eur > 0 ? t.eur.toFixed(2) : "—"}
                        </td>
                        <td className="p-3 text-right tabular-nums text-muted-foreground">
                          {t.chf_as_eur > 0 ? t.chf_as_eur.toFixed(2) : "—"}
                        </td>
                        <td className="p-3 text-right tabular-nums font-semibold">
                          {t.total_eur.toFixed(2)} €
                        </td>
                        <td className="p-3 text-right">
                          <Button variant="ghost" size="sm" onClick={() => dl(`/payroll/teacher/${encodeURIComponent(t.name)}/pdf`, `recap_${t.name}.pdf`, t.name)} disabled={!!downloading}>
                            {downloading === t.name ? <Loader2 className="animate-spin" /> : <Download />}
                          </Button>
                        </td>
                      </tr>
                    ))}
                </tbody>
                <tfoot className="bg-secondary/30">
                  <tr>
                    <td colSpan={5} className="p-3 text-right font-semibold">Grand total</td>
                    <td className="p-3 text-right tabular-nums font-bold text-success">
                      {summary?.grand_total.toFixed(2)} €
                    </td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
