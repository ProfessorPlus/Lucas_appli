import Link from "next/link";
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
} from "lucide-react";

import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { MultiCurrencyTotal } from "@/components/shared/MultiCurrencyTotal";
import { WorkflowStepper } from "@/components/shared/WorkflowStepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

// Données fake — seront remplacées par fetch /api/dashboard/summary
// Exemple aligné sur Avril 2026 (Streamlit) pour comparaison côte à côte.
const FAKE = {
  professors: 12,
  families: 47,
  toBill: { EUR: 3658, CHF: 6108, AED: 1322 },
  caTotalEur: 10595, // CHF + EUR + AED convertis (Frankfurter)
  profsEur: 5441,
  netEur: 5154, // CA total EUR − Profs EUR (CORRIGÉ — incluait pas AED avant)
  trend: 12.4,
};

export default function HomePage() {
  return (
    <div className="space-y-8">
      <PageHeader
        variant="primary"
        icon={<GraduationCap className="h-6 w-6" />}
        title="Bienvenue sur Professor+"
        subtitle="L'admin tout-en-un de ton activité de soutien scolaire"
        actions={
          <Button asChild variant="accent">
            <Link href="/extract">
              <Sparkles /> Lancer le workflow
            </Link>
          </Button>
        }
      />

      {/* 4 metrics principales */}
      <div className="grid gap-4 lg:grid-cols-4">
        <StatsCard
          label="Professeurs"
          value={FAKE.professors}
          hint="10 TutorBird + 2 Notion"
          icon={<Users className="h-5 w-5" />}
          tone="primary"
          delay={0}
        />
        <StatsCard
          label="Familles"
          value={FAKE.families}
          hint="Mois en cours"
          icon={<GraduationCap className="h-5 w-5" />}
          tone="accent"
          delay={0.05}
        />
        <StatsCard
          label="À facturer"
          value={<MultiCurrencyTotal size="md" amounts={FAKE.toBill} />}
          hint={`≈ ${FAKE.caTotalEur.toLocaleString("fr-FR")} € brut`}
          footer={`Net : ${FAKE.netEur.toLocaleString("fr-FR")} €`}
          icon={<Wallet className="h-5 w-5" />}
          tone="warning"
          delay={0.1}
        />
        <StatsCard
          label="Net EUR"
          value={`${FAKE.netEur.toLocaleString("fr-FR")} €`}
          hint={`CA ${FAKE.caTotalEur.toLocaleString("fr-FR")} € − Profs ${FAKE.profsEur.toLocaleString("fr-FR")} €`}
          icon={<TrendingUp className="h-5 w-5" />}
          tone="emerald"
          trend={{ value: FAKE.trend, positive: true }}
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

      {/* Workflow + Activité */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Workflow recommandé</CardTitle>
            <CardDescription>État du mois en cours</CardDescription>
          </CardHeader>
          <CardContent>
            <WorkflowStepper
              steps={[
                { label: "Extraire les leçons", status: "done" },
                { label: "Créer les liens de paiement", status: "done" },
                { label: "Générer les factures PDF", status: "active" },
                { label: "Envoyer les factures", status: "pending" },
                { label: "Rappels J+10/J+20/J+30", status: "pending" },
                { label: "Récap paie profs", status: "pending" },
              ]}
            />
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-card to-secondary/30">
          <CardHeader>
            <CardTitle>👋 Démarrage</CardTitle>
            <CardDescription>
              Tu travailles sur la nouvelle interface. L'app Streamlit reste disponible en backup.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-foreground">
              Toutes les données sont mockées pour l'instant. Le backend FastAPI + endpoints
              seront branchés étape par étape, en commençant par l'extraction TutorBird.
            </p>
            <div className="flex gap-2 pt-2">
              <Button asChild variant="outline" size="sm">
                <Link href="/showcase">
                  <Sparkles /> Voir le design system
                </Link>
              </Button>
              <Button asChild size="sm">
                <Link href="/extract">
                  Continuer <ArrowRight />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
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
      <div className={`flex h-12 w-12 items-center justify-center rounded-xl ring-1 transition-transform group-hover:scale-105 ${styles}`}>
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
