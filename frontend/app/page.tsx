"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  GraduationCap,
  Users,
  Wallet,
  TrendingUp,
  Sparkles,
  Download,
  CreditCard,
  FileText,
  ArrowRight,
  Inbox,
  Bell,
  Send,
  CalendarDays,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { motion } from "framer-motion";

import {
  api,
  type DashboardSummary,
  type InvoiceFolder,
  type DashboardPayments,
  type DashboardEmails,
  type RandomQuotes,
} from "@/lib/api";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { MultiCurrencyTotal } from "@/components/shared/MultiCurrencyTotal";
import { WorkflowStepper } from "@/components/shared/WorkflowStepper";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export default function HomePage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [folders, setFolders] = useState<InvoiceFolder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [payments, setPayments] = useState<DashboardPayments | null>(null);
  const [emails, setEmails] = useState<DashboardEmails | null>(null);
  const [quotes, setQuotes] = useState<RandomQuotes | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<DashboardSummary>("/dashboard/summary"),
      api.get<InvoiceFolder[]>("/invoice-folders"),
      api.get<DashboardEmails>("/dashboard/emails").catch(() => null),
      api.get<RandomQuotes>("/quotes/random").catch(() => null),
    ])
      .then(([s, f, e, q]) => {
        setSummary(s);
        setFolders(f);
        if (f.length > 0) setSelectedFolder(f[0].month);
        setEmails(e);
        setQuotes(q);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Erreur"));
  }, []);

  useEffect(() => {
    if (!selectedFolder) return;
    api
      .get<DashboardPayments>(
        `/dashboard/payments?folder=${encodeURIComponent(selectedFolder)}`,
      )
      .then(setPayments)
      .catch(() => setPayments(null));
  }, [selectedFolder]);

  const workflowSteps = useMemo(() => {
    const hasExtraction = !!summary?.extraction_end;
    return [
      { label: "Extraire les leçons", status: (hasExtraction ? "done" : "active") as "done" | "active" | "pending" },
      { label: "Créer les liens de paiement", status: (hasExtraction ? "active" : "pending") as "done" | "active" | "pending" },
      { label: "Générer les factures PDF", status: "pending" as const },
      { label: "Envoyer les factures", status: "pending" as const },
      { label: "Rappels J+10 / J+20 / J+30", status: "pending" as const },
    ];
  }, [summary]);

  return (
    <div className="space-y-8">
      <PageHeader
        variant="primary"
        icon={<GraduationCap className="h-6 w-6" />}
        title="Bienvenue sur Professor+"
        subtitle={
          summary?.extraction_end
            ? `Dernière extraction : ${summary.extraction_end}`
            : "L'admin tout-en-un de ton activité de soutien scolaire"
        }
        actions={
          <Button asChild variant="accent">
            <Link href="/extract">
              <Sparkles /> Lancer le workflow
            </Link>
          </Button>
        }
      />

      {error && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex items-start gap-2 py-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4" />
            Impossible de charger le dashboard : {error}
          </CardContent>
        </Card>
      )}

      {/* 4 metrics principales */}
      <div className="grid gap-4 lg:grid-cols-4">
        <StatsCard
          label="Professeurs"
          value={summary?.nb_profs ?? "—"}
          hint={
            summary
              ? `${summary.nb_profs_breakdown.tutorbird_or_secrets} TutorBird · ${summary.nb_profs_breakdown.notion_only} Notion`
              : "Chargement…"
          }
          icon={<Users className="h-5 w-5" />}
          tone="primary"
          delay={0}
        />
        <StatsCard
          label="Familles"
          value={summary?.nb_families ?? "—"}
          hint={summary?.extraction_end ? `Au ${summary.extraction_end}` : "Aucune extraction"}
          icon={<GraduationCap className="h-5 w-5" />}
          tone="accent"
          delay={0.05}
        />
        <StatsCard
          label="À facturer"
          value={
            summary && Object.keys(summary.amounts_by_currency).length > 0 ? (
              <MultiCurrencyTotal size="md" amounts={summary.amounts_by_currency} />
            ) : (
              "—"
            )
          }
          hint={summary ? `≈ ${formatEur(summary.ca_total_eur)} brut` : undefined}
          footer={summary ? `Net : ${formatEur(summary.net_eur)}` : undefined}
          icon={<Wallet className="h-5 w-5" />}
          tone="warning"
          delay={0.1}
        />
        <StatsCard
          label="Net EUR"
          value={summary ? formatEur(summary.net_eur) : "—"}
          hint={
            summary
              ? `CA ${formatEur(summary.ca_total_eur)} − Profs ${formatEur(summary.profs_total_eur)}`
              : undefined
          }
          icon={<TrendingUp className="h-5 w-5" />}
          tone="emerald"
          delay={0.15}
        />
      </div>

      {/* Quick actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <QuickAction
          href="/extract"
          icon={<Download className="h-5 w-5" />}
          title="Extraire les leçons"
          subtitle="TutorBird + Notion hors TB"
          tone="sky"
        />
        <QuickAction
          href="/payment-links"
          icon={<CreditCard className="h-5 w-5" />}
          title="Créer liens de paiement"
          subtitle="Avec impayés n-2"
          tone="accent"
        />
        <QuickAction
          href="/invoices"
          icon={<FileText className="h-5 w-5" />}
          title="Générer les factures"
          subtitle="PDFs + envoi"
          tone="violet"
        />
      </div>

      {/* Suivi des paiements */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-accent" />
                Suivi des paiements
              </CardTitle>
              <CardDescription>
                Statut des factures pour un dossier donné (Notion).
              </CardDescription>
            </div>
            <select
              value={selectedFolder ?? ""}
              onChange={(e) => setSelectedFolder(e.target.value || null)}
              disabled={folders.length === 0}
              className="h-10 rounded-lg border border-border bg-card px-3 text-sm"
            >
              {folders.length === 0 ? (
                <option>Aucun dossier</option>
              ) : (
                folders.map((f) => (
                  <option key={f.id} value={f.month}>
                    {f.month}
                  </option>
                ))
              )}
            </select>
          </div>
        </CardHeader>
        <CardContent>
          {payments && payments.total > 0 ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <Mini label="Payées" value={payments.paid} tone="success" icon={<CheckCircle2 />} />
                <Mini label="En attente" value={payments.unpaid} tone={payments.unpaid > 0 ? "warning" : "success"} icon={<Inbox />} />
                <Mini label="Progression" value={`${payments.paid}/${payments.total}`} tone="primary" />
              </div>
              <div>
                <div className="mb-1.5 flex justify-between text-xs">
                  <span className="text-muted-foreground">Avancement</span>
                  <span className="font-medium tabular-nums">{payments.pct}%</span>
                </div>
                <Progress value={payments.pct} />
              </div>
              {Object.keys(payments.amounts_by_currency_paid).length > 0 && (
                <div className="grid gap-3 rounded-lg border border-border bg-secondary/30 p-3 sm:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Encaissé</p>
                    <MultiCurrencyTotal size="sm" amounts={payments.amounts_by_currency_paid} />
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">Dû total</p>
                    <MultiCurrencyTotal size="sm" amounts={payments.amounts_by_currency_due} />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {payments?.error
                ? `${payments.error}`
                : folders.length === 0
                  ? "Aucun dossier de factures. Lance d'abord une génération de factures."
                  : "Aucune ligne Notion trouvée pour ce dossier."}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Historique envois */}
      {emails && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Mini
            label="Dernier envoi factures"
            value={emails.invoice_sent_date ?? "—"}
            tone="cyan"
            icon={<Send />}
            size="md"
          />
          <Mini
            label="Dernier rappel"
            value={emails.reminder_sent_date ?? "—"}
            tone="tangerine"
            icon={<Bell />}
            size="md"
          />
          <Mini
            label="Nb relances"
            value={emails.reminder_count}
            tone={emails.reminder_count > 0 ? "amber" : "primary"}
            icon={<CalendarDays />}
            size="md"
          />
        </div>
      )}

      {/* Workflow + Quotes */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Workflow recommandé</CardTitle>
            <CardDescription>Étapes pour clore le mois</CardDescription>
          </CardHeader>
          <CardContent>
            <WorkflowStepper steps={workflowSteps} />
          </CardContent>
        </Card>

        {quotes && (
          <div className="space-y-4">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="overflow-hidden rounded-xl bg-gradient-to-br from-[#1a5632] to-[#2d8a56] p-5 text-white shadow-md"
            >
              <p className="text-xs uppercase tracking-wider opacity-80">🕌 Hadith du jour</p>
              <p className="mt-2 text-sm leading-relaxed italic">« {quotes.hadith.text} »</p>
              <p className="mt-2 text-xs opacity-80">
                — {quotes.hadith.narrator} · {quotes.hadith.source}
              </p>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="overflow-hidden rounded-xl bg-gradient-to-br from-[#1a3a5c] to-[#2a5a8c] p-5 text-white shadow-md"
            >
              <p className="text-xs uppercase tracking-wider opacity-80">💡 Citation du jour</p>
              <p className="mt-2 text-sm leading-relaxed italic">"{quotes.quote.text}"</p>
              <p className="mt-2 text-xs opacity-80">— {quotes.quote.author}</p>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatEur(n: number): string {
  return `${n.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} €`;
}

function Mini({
  label,
  value,
  tone = "primary",
  icon,
  size = "sm",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "primary" | "success" | "warning" | "cyan" | "tangerine" | "amber";
  icon?: React.ReactNode;
  size?: "sm" | "md";
}) {
  const styles = {
    primary: "text-primary",
    success: "text-success",
    warning: "text-warning",
    cyan: "text-[#06B6D4]",
    tangerine: "text-[#F97316]",
    amber: "text-[#F59E0B]",
  }[tone];

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
        {icon && <span className={`${styles} [&_svg]:h-3.5 [&_svg]:w-3.5`}>{icon}</span>}
        {label}
      </div>
      <div className={`mt-1.5 font-bold ${size === "md" ? "text-lg" : "text-2xl"} ${styles}`}>
        {value}
      </div>
    </div>
  );
}

function QuickAction({
  href,
  icon,
  title,
  subtitle,
  tone,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  tone: "sky" | "accent" | "violet";
}) {
  const styles = {
    sky: "bg-[#3B82F6]/10 text-[#3B82F6] ring-[#3B82F6]/20",
    accent: "bg-accent/10 text-accent ring-accent/20",
    violet: "bg-[#8B5CF6]/10 text-[#8B5CF6] ring-[#8B5CF6]/20",
  }[tone];

  return (
    <Link
      href={href}
      className="group flex items-center gap-4 rounded-xl border border-border bg-card p-5 shadow-[0_1px_3px_rgba(15,27,45,0.04)] transition-all hover:border-accent/40 hover:shadow-md"
    >
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-xl ring-1 transition-transform group-hover:scale-105 ${styles}`}
      >
        {icon}
      </div>
      <div className="flex-1">
        <p className="font-semibold text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
    </Link>
  );
}
