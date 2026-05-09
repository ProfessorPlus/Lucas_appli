"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Download,
  RefreshCw,
  Calendar,
  Users,
  GraduationCap,
  Wallet,
  TrendingUp,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";

import {
  api,
  type ExtractRequest,
  type ExtractSummary,
  type NotionProfEntry,
  type NotionProfsResponse,
} from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { MultiCurrencyTotal } from "@/components/shared/MultiCurrencyTotal";
import { FXRateBadge } from "@/components/shared/FXRateBadge";
import { JobRunner } from "@/components/shared/JobRunner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── helpers ───────────────────────────────────────────────────────────────

function pad(n: number) {
  return String(n).padStart(2, "0");
}
function isoDay(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function monthRange(offset: number): { start: string; end: string; label: string } {
  const now = new Date();
  const target = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const start = new Date(target.getFullYear(), target.getMonth(), 1);
  const end = new Date(target.getFullYear(), target.getMonth() + 1, 0);
  const label = target.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  return { start: isoDay(start), end: isoDay(end), label };
}

// ── page ──────────────────────────────────────────────────────────────────

export default function ExtractPage() {
  const today = useMemo(() => isoDay(new Date()), []);
  const previousMonth = useMemo(() => monthRange(-1), []);

  // ── form state ─────────────────────────────────────────────────────────
  const [startDate, setStartDate] = useState(previousMonth.start);
  const [endDate, setEndDate] = useState(previousMonth.end);
  const [allDay, setAllDay] = useState(true);
  const [startTime, setStartTime] = useState("00:00");
  const [endTime, setEndTime] = useState("23:59");

  // ── notion state ───────────────────────────────────────────────────────
  const [notionEntries, setNotionEntries] = useState<NotionProfEntry[] | null>(null);
  const [notionLoading, setNotionLoading] = useState(false);
  const [notionError, setNotionError] = useState<string | null>(null);
  const [includeNotion, setIncludeNotion] = useState(true);
  const [selectedNotionIds, setSelectedNotionIds] = useState<Set<string>>(new Set());

  // ── job + result state ─────────────────────────────────────────────────
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [summary, setSummary] = useState<ExtractSummary | null>(null);

  // ── load Notion entries on mount ───────────────────────────────────────
  useEffect(() => {
    void refreshNotion();
    // also try to load the last summary from a previous run
    api
      .get<ExtractSummary>("/extract/last-summary")
      .then((s) => setSummary(s))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshNotion() {
    setNotionLoading(true);
    setNotionError(null);
    try {
      const res = await api.get<NotionProfsResponse>("/notion/profs-hors-tb");
      if (!res.success) {
        setNotionError(res.error || "Erreur Notion");
        setNotionEntries([]);
        return;
      }
      setNotionEntries(res.entries);
      setSelectedNotionIds(new Set(res.entries.map((e) => e.page_id)));
    } catch (err) {
      setNotionError(err instanceof Error ? err.message : "Erreur réseau");
      setNotionEntries([]);
    } finally {
      setNotionLoading(false);
    }
  }

  function toggleNotion(pageId: string) {
    setSelectedNotionIds((prev) => {
      const next = new Set(prev);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  }

  function applyQuickPick(offset: number) {
    const { start, end } = monthRange(offset);
    setStartDate(start);
    setEndDate(end);
  }

  async function launch() {
    if (submitting) return;
    setSubmitting(true);
    setJobId(null);
    setSummary(null);
    try {
      const body: ExtractRequest = {
        start_date: startDate,
        end_date: endDate,
        start_time: allDay ? "00:00" : startTime,
        end_time: allDay ? "23:59" : endTime,
        notion_prof_page_ids: includeNotion
          ? Array.from(selectedNotionIds)
          : null,
      };
      const res = await api.post<{ job_id: string }>("/extract", body);
      setJobId(res.job_id);
      toast.success(`Extraction démarrée — job ${res.job_id.slice(0, 8)}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Erreur inconnue";
      toast.error(`Échec du démarrage : ${msg}`);
    } finally {
      setSubmitting(false);
    }
  }

  // ── filtered notion total (preview before launch) ──────────────────────
  const notionPreview = useMemo(() => {
    if (!notionEntries) return null;
    const selected = notionEntries.filter((e) => selectedNotionIds.has(e.page_id));
    const totals: Record<string, number> = {};
    let totalHours = 0;
    for (const e of selected) {
      const cur = (e.devise_client || "EUR").toUpperCase();
      const amount = (e.heures_faites || 0) * (e.taux_horaire_client || 0);
      totals[cur] = (totals[cur] || 0) + amount;
      totalHours += e.heures_faites || 0;
    }
    return { count: selected.length, hours: totalHours, totals };
  }, [notionEntries, selectedNotionIds]);

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        variant="primary"
        icon={<Download className="h-6 w-6" />}
        title="Extraction TutorBird"
        subtitle="Récupère les leçons d'une période, fusionne avec les profs hors TutorBird, calcule le CA et le net EUR."
      />

      {/* ── PERIOD ───────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-accent" />
            Période
          </CardTitle>
          <CardDescription>Sélectionne le mois à extraire (TutorBird + Notion).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Quick picks */}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => applyQuickPick(-2)}>
              {monthRange(-2).label}
            </Button>
            <Button variant="outline" size="sm" onClick={() => applyQuickPick(-1)}>
              {monthRange(-1).label} <Badge variant="accent" className="ml-1.5 text-[10px]">recommandé</Badge>
            </Button>
            <Button variant="outline" size="sm" onClick={() => applyQuickPick(0)}>
              {monthRange(0).label}
            </Button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="start-date">Date de début</Label>
              <Input
                id="start-date"
                type="date"
                value={startDate}
                max={today}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="end-date">Date de fin</Label>
              <Input
                id="end-date"
                type="date"
                value={endDate}
                max={today}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
            <div className="flex items-center gap-3">
              <Switch id="all-day" checked={allDay} onCheckedChange={setAllDay} />
              <Label htmlFor="all-day" className="cursor-pointer normal-case tracking-normal text-sm font-medium text-foreground">
                Journée entière (00:00 → 23:59)
              </Label>
            </div>
            {!allDay && (
              <div className="flex items-center gap-2">
                <Input
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-28"
                />
                <span className="text-muted-foreground">→</span>
                <Input
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  className="w-28"
                />
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── NOTION HORS TB ───────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-accent" />
                Profs hors TutorBird (Notion)
              </CardTitle>
              <CardDescription>
                Familles ajoutées manuellement dans Notion qui doivent être incluses.
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Switch
                  id="include-notion"
                  checked={includeNotion}
                  onCheckedChange={setIncludeNotion}
                />
                <Label htmlFor="include-notion" className="cursor-pointer normal-case tracking-normal text-xs">
                  Inclure
                </Label>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshNotion}
                disabled={notionLoading}
              >
                {notionLoading ? <Loader2 className="animate-spin" /> : <RefreshCw />} Rafraîchir
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {notionError ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Impossible de charger Notion</p>
                <p className="text-xs opacity-90">{notionError}</p>
              </div>
            </div>
          ) : notionLoading && !notionEntries ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
            </div>
          ) : notionEntries && notionEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune entrée dans Notion.</p>
          ) : notionEntries ? (
            <div className={cn("space-y-3", !includeNotion && "opacity-50 pointer-events-none")}>
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="w-10 p-3"></th>
                      <th className="p-3 text-left font-semibold">Famille</th>
                      <th className="p-3 text-left font-semibold">Prof</th>
                      <th className="p-3 text-left font-semibold">Élève</th>
                      <th className="p-3 text-right font-semibold">Heures</th>
                      <th className="p-3 text-right font-semibold">Taux client</th>
                      <th className="p-3 text-right font-semibold">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notionEntries.map((e) => {
                      const total = (e.heures_faites || 0) * (e.taux_horaire_client || 0);
                      const cur = (e.devise_client || "EUR").toUpperCase();
                      return (
                        <tr key={e.page_id} className="border-t border-border">
                          <td className="p-3">
                            <Checkbox
                              checked={selectedNotionIds.has(e.page_id)}
                              onCheckedChange={() => toggleNotion(e.page_id)}
                            />
                          </td>
                          <td className="p-3 font-medium">{e.famille || "—"}</td>
                          <td className="p-3 text-muted-foreground">{e.professeur || "—"}</td>
                          <td className="p-3 text-muted-foreground">{e.eleve || "—"}</td>
                          <td className="p-3 text-right tabular-nums">
                            {(e.heures_faites || 0).toFixed(1)} h
                          </td>
                          <td className="p-3 text-right tabular-nums text-muted-foreground">
                            {e.taux_horaire_client?.toFixed(0) || 0} {cur}
                          </td>
                          <td className="p-3 text-right tabular-nums font-semibold">
                            {total.toFixed(0)} {cur}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {notionPreview && notionPreview.count > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    {notionPreview.count} sélectionné(s) · {notionPreview.hours.toFixed(1)} h
                  </span>
                  <MultiCurrencyTotal size="sm" amounts={notionPreview.totals} />
                </div>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ── LAUNCH ───────────────────────────────────────────────────── */}
      <div className="flex justify-end">
        <Button
          variant="accent"
          size="lg"
          onClick={launch}
          disabled={submitting || !!jobId}
        >
          {submitting ? <Loader2 className="animate-spin" /> : <Download />}
          Lancer l'extraction
        </Button>
      </div>

      {/* ── JOB RUNNER ───────────────────────────────────────────────── */}
      {jobId && (
        <Card>
          <CardHeader>
            <CardTitle>Job en cours</CardTitle>
          </CardHeader>
          <CardContent>
            <JobRunner<ExtractSummary>
              jobId={jobId}
              onDone={(result) => {
                setSummary(result);
                toast.success("Extraction terminée 🎉");
              }}
              onError={(err) => {
                toast.error(`Échec : ${err}`);
              }}
              onCancel={() => setJobId(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* ── RESULTS ──────────────────────────────────────────────────── */}
      {summary && <ResultsSection summary={summary} />}
    </div>
  );
}

function ResultsSection({ summary }: { summary: ExtractSummary }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-5"
    >
      <div className="flex items-center gap-2 text-sm">
        <CheckCircle2 className="h-4 w-4 text-success" />
        <span className="font-semibold text-foreground">
          Dernière extraction — {summary.extraction_end}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <StatsCard
          label="Familles"
          value={summary.families}
          hint={summary.notion_added > 0 ? `dont ${summary.notion_added} via Notion` : undefined}
          icon={<GraduationCap className="h-5 w-5" />}
          tone="primary"
          delay={0}
        />
        <StatsCard
          label="Leçons"
          value={summary.lessons}
          icon={<Users className="h-5 w-5" />}
          tone="accent"
          delay={0.05}
        />
        <StatsCard
          label="À facturer"
          value={<MultiCurrencyTotal size="md" amounts={summary.amounts_by_currency} />}
          hint={`≈ ${summary.ca_total_eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} € brut`}
          footer={`Net : ${summary.net_eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €`}
          icon={<Wallet className="h-5 w-5" />}
          tone="warning"
          delay={0.1}
        />
        <StatsCard
          label="Net EUR"
          value={`${summary.net_eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €`}
          hint={`CA ${summary.ca_total_eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} € − Profs ${summary.profs_total_eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €`}
          icon={<TrendingUp className="h-5 w-5" />}
          tone="emerald"
          delay={0.15}
        />
      </div>

      {summary.fx && (summary.fx.chf_eur || summary.fx.aed_eur) && (
        <div className="flex flex-wrap gap-2">
          {summary.fx.chf_eur && (
            <FXRateBadge pair="CHF→EUR" rate={summary.fx.chf_eur} source="frankfurter" />
          )}
          {summary.fx.aed_eur && (
            <FXRateBadge pair="AED→EUR" rate={summary.fx.aed_eur} source="frankfurter" />
          )}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Détail par famille</CardTitle>
          <CardDescription>
            Vérification devise · les familles marquées EUR sont définies dans{" "}
            <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">familles_euros.yaml</code>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="p-3 text-left font-semibold">Famille</th>
                  <th className="p-3 text-right font-semibold">EUR</th>
                  <th className="p-3 text-right font-semibold">CHF</th>
                  <th className="p-3 text-right font-semibold">AED</th>
                  <th className="p-3 text-center font-semibold">Note</th>
                </tr>
              </thead>
              <tbody>
                {summary.details_by_family.map((f) => (
                  <tr key={f.family_id} className="border-t border-border">
                    <td className="p-3 font-medium">{f.parent_name}</td>
                    <td className="p-3 text-right tabular-nums">
                      {f.EUR > 0 ? f.EUR.toFixed(2) : "—"}
                    </td>
                    <td className="p-3 text-right tabular-nums">
                      {f.CHF > 0 ? f.CHF.toFixed(2) : "—"}
                    </td>
                    <td className="p-3 text-right tabular-nums">
                      {f.AED > 0 ? f.AED.toFixed(2) : "—"}
                    </td>
                    <td className="p-3 text-center">
                      {f.is_euro && <Badge variant="accent" className="text-[10px]">EUR forcé</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
