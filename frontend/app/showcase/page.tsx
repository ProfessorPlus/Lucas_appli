"use client";

import { useEffect, useState } from "react";
import {
  Users,
  GraduationCap,
  Wallet,
  TrendingUp,
  Sparkles,
  Mail,
  CreditCard,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Info,
  XCircle,
  Send,
  Inbox,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/PageHeader";
import { StatsCard } from "@/components/shared/StatsCard";
import { MultiCurrencyTotal } from "@/components/shared/MultiCurrencyTotal";
import { FXRateBadge } from "@/components/shared/FXRateBadge";
import { TerminalLog } from "@/components/shared/TerminalLog";
import { EmptyState } from "@/components/shared/EmptyState";
import { WorkflowStepper } from "@/components/shared/WorkflowStepper";
import { ActivityTimeline } from "@/components/shared/ActivityTimeline";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

const PALETTE = [
  { name: "Primary", hsl: "219 54% 26%", hex: "#1F3A67", className: "bg-primary" },
  { name: "Accent", hsl: "168 80% 40%", hex: "#14B8A6", className: "bg-accent" },
  { name: "Background", hsl: "210 20% 98%", hex: "#F7F9FA", className: "bg-background border" },
  { name: "Foreground", hsl: "222 47% 11%", hex: "#0F1B2D", className: "bg-foreground" },
  { name: "Card", hsl: "0 0% 100%", hex: "#FFFFFF", className: "bg-card border" },
  { name: "Secondary", hsl: "210 18% 95%", hex: "#EEF1F4", className: "bg-secondary" },
  { name: "Muted FG", hsl: "215 16% 47%", hex: "#697080", className: "bg-muted-foreground" },
  { name: "Border", hsl: "214 20% 90%", hex: "#DDE3EC", className: "bg-border" },
  { name: "Success", hsl: "142 71% 45%", hex: "#29C76F", className: "bg-success" },
  { name: "Warning", hsl: "38 92% 50%", hex: "#F59E0B", className: "bg-warning" },
  { name: "Info", hsl: "199 89% 48%", hex: "#0EA5E9", className: "bg-info" },
  { name: "Destructive", hsl: "0 84% 60%", hex: "#F35454", className: "bg-destructive" },
  { name: "Sidebar bg", hsl: "225 25% 14%", hex: "#1A1F2E", className: "bg-sidebar" },
  { name: "Sidebar accent", hsl: "225 20% 20%", hex: "#282E3F", className: "bg-sidebar-accent" },
];

const COMPONENT_PALETTE = [
  { name: "Émeraude", hex: "#10B981", usage: "Payé, connecté" },
  { name: "Ambre", hex: "#F59E0B", usage: "Retard, warning" },
  { name: "Bleu", hex: "#3B82F6", usage: "Extraction" },
  { name: "Violet", hex: "#8B5CF6", usage: "Factures" },
  { name: "Cyan", hex: "#06B6D4", usage: "Emails" },
  { name: "Orange", hex: "#F97316", usage: "Rappels" },
  { name: "Terminal", hex: "#0D1117", usage: "Logs background" },
];

export default function ShowcasePage() {
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const sample = [
      "🚀 Démarrage de l'extraction TutorBird",
      "🔍 Connexion à TutorBird API...",
      "✅ Authentification réussie",
      "📥 Récupération des leçons (mois en cours)",
      "🔍 12 profs détectés, 47 familles, 312 leçons",
      "ℹ️ Conversion CHF→EUR : 1 CHF = 1.0712 EUR (Frankfurter)",
      "ℹ️ Conversion AED→EUR via peg USD : 1 AED = 0.2531 EUR",
      "✅ Extraction terminée — 312 leçons importées",
      "💰 Total : 6,445.00 CHF + 3,658.32 EUR + 1,321.80 AED",
      "💶 Net EUR : 7,234.18 € (CA 10,892 € − Profs 3,658 €)",
    ];

    let i = 0;
    const interval = setInterval(() => {
      if (i < sample.length) {
        setLogs((prev) => [...prev, sample[i]]);
        setProgress(((i + 1) / sample.length) * 100);
        i++;
      } else {
        clearInterval(interval);
      }
    }, 600);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-12 pb-16">
      <PageHeader
        variant="primary"
        icon={<Sparkles className="h-6 w-6" />}
        title="Design System — Professor+"
        subtitle="Catalogue de tous les composants et tokens. À valider avant de construire les 12 pages réelles."
      />

      {/* Palette principale */}
      <Section title="🎨 Palette principale" subtitle="Tokens HSL définis dans tailwind.config.ts + globals.css">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {PALETTE.map((c) => (
            <div key={c.name} className="overflow-hidden rounded-lg border border-border bg-card">
              <div className={`${c.className} h-16`} />
              <div className="p-3">
                <p className="text-sm font-semibold text-foreground">{c.name}</p>
                <p className="font-mono text-[11px] text-muted-foreground">{c.hex}</p>
                <p className="font-mono text-[10px] text-muted-foreground/70">{c.hsl}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Palette catégorielle */}
      <Section title="🏷️ Couleurs catégorielles" subtitle="Utilisées pour les badges et icônes contextuels">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
          {COMPONENT_PALETTE.map((c) => (
            <div key={c.name} className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="h-12" style={{ background: c.hex }} />
              <div className="p-3">
                <p className="text-sm font-semibold text-foreground">{c.name}</p>
                <p className="font-mono text-[11px] text-muted-foreground">{c.hex}</p>
                <p className="text-[10px] text-muted-foreground/70">{c.usage}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Stats Cards */}
      <Section title="📊 Stats Cards" subtitle="Composant principal du dashboard. 11 tons disponibles.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard
            label="Professeurs"
            value="12"
            hint="10 TutorBird + 2 Notion"
            icon={<Users className="h-5 w-5" />}
            tone="primary"
            delay={0}
          />
          <StatsCard
            label="Familles"
            value="47"
            hint="Mois en cours"
            icon={<GraduationCap className="h-5 w-5" />}
            tone="accent"
            delay={0.05}
          />
          <StatsCard
            label="À facturer"
            value={
              <MultiCurrencyTotal
                size="lg"
                amounts={{ EUR: 3658.32, CHF: 6445.0, AED: 1321.8 }}
              />
            }
            icon={<Wallet className="h-5 w-5" />}
            tone="warning"
            delay={0.1}
          />
          <StatsCard
            label="Net EUR"
            value="7,234.18 €"
            hint="CA 10,892 € − Profs 3,658 €"
            icon={<TrendingUp className="h-5 w-5" />}
            tone="emerald"
            trend={{ value: 12.4, positive: true }}
            delay={0.15}
          />
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard label="Extractions" value="3" icon={<FileText className="h-5 w-5" />} tone="sky" />
          <StatsCard label="Factures" value="47" icon={<FileText className="h-5 w-5" />} tone="violet" />
          <StatsCard label="Emails envoyés" value="42" icon={<Mail className="h-5 w-5" />} tone="cyan" />
          <StatsCard label="Rappels" value="5" icon={<Inbox className="h-5 w-5" />} tone="tangerine" />
        </div>
      </Section>

      {/* MultiCurrencyTotal & FXRateBadge */}
      <Section title="💱 Multi-devise & taux FX" subtitle="Cas critique A du spec — calcul leçon par leçon">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>MultiCurrencyTotal</CardTitle>
              <CardDescription>Affichage des sommes en plusieurs devises</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Taille small
                </p>
                <MultiCurrencyTotal size="sm" amounts={{ EUR: 1037, AED: 1322 }} />
              </div>
              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Taille medium
                </p>
                <MultiCurrencyTotal size="md" amounts={{ EUR: 3658.32, CHF: 6445.0 }} />
              </div>
              <div>
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                  Taille large
                </p>
                <MultiCurrencyTotal
                  size="lg"
                  amounts={{ EUR: 3658.32, CHF: 6445.0, AED: 1321.8 }}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>FXRateBadge</CardTitle>
              <CardDescription>Source de taux avec fallback chain</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <FXRateBadge pair="CHF→EUR" rate={1.0712} source="frankfurter" />
              <FXRateBadge pair="USD→EUR" rate={0.9234} source="ecb" />
              <FXRateBadge pair="AED→USD" rate={3.6725} source="hardcoded" />
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* Buttons & Badges */}
      <Section title="🔘 Boutons & Badges">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Boutons</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => toast.success("Action réussie")}>Default</Button>
                <Button variant="accent" onClick={() => toast.info("Action turquoise")}>
                  <Sparkles /> Accent
                </Button>
                <Button variant="outline">Outline</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="destructive" onClick={() => toast.error("Suppression")}>
                  Destructive
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm">Small</Button>
                <Button>Default</Button>
                <Button size="lg">Large</Button>
                <Button size="icon" variant="outline">
                  <Send />
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Badges sémantiques</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Badge variant="default">Default</Badge>
              <Badge variant="secondary">Secondary</Badge>
              <Badge variant="accent">
                <Sparkles className="h-3 w-3" /> Accent
              </Badge>
              <Badge variant="success">
                <CheckCircle2 className="h-3 w-3" /> Payé
              </Badge>
              <Badge variant="warning">
                <AlertTriangle className="h-3 w-3" /> En attente
              </Badge>
              <Badge variant="info">
                <Info className="h-3 w-3" /> Info
              </Badge>
              <Badge variant="destructive">
                <XCircle className="h-3 w-3" /> Erreur
              </Badge>
              <Badge variant="outline">Outline</Badge>
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* Progress & cards de paiement */}
      <Section title="📈 Progress & cards de paiement" subtitle="Composant pour le dashboard accueil">
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">% payé</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold tabular-nums text-foreground">73%</p>
              <p className="mt-1 text-xs text-muted-foreground">34 / 47 factures</p>
              <Progress value={73} className="mt-3" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">Montant payé</CardTitle>
            </CardHeader>
            <CardContent>
              <MultiCurrencyTotal
                size="md"
                amounts={{ EUR: 2671.5, CHF: 4703.85 }}
              />
              <p className="mt-2 text-xs text-muted-foreground">sur 7,425 € total</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">Reste à encaisser</CardTitle>
            </CardHeader>
            <CardContent>
              <MultiCurrencyTotal
                size="md"
                amounts={{ EUR: 986.82, CHF: 1741.15, AED: 1321.8 }}
              />
              <p className="mt-2 text-xs text-warning">⚠️ 5 familles &gt; 30 jours</p>
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* Workflow stepper + Activity timeline */}
      <Section title="🚀 Workflow & Activité">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Workflow recommandé</CardTitle>
              <CardDescription>État du mois en cours</CardDescription>
            </CardHeader>
            <CardContent>
              <WorkflowStepper
                steps={[
                  { label: "Extraire les leçons", description: "TutorBird + Notion hors TB", status: "done" },
                  { label: "Créer les liens de paiement", description: "Avec impayés n-2", status: "done" },
                  { label: "Générer les factures PDF", description: "47 familles", status: "active" },
                  { label: "Envoyer les factures", description: "4 templates : FR, EN, Carole, Multi", status: "pending" },
                  { label: "Rappels paiement", description: "À J+10, J+20, J+30", status: "pending" },
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Activité récente</CardTitle>
            </CardHeader>
            <CardContent>
              <ActivityTimeline
                items={[
                  {
                    icon: <CheckCircle2 className="h-4 w-4" />,
                    title: "Paiement reçu — Calabresi A.",
                    description: "315 € via Stripe webhook",
                    timestamp: "il y a 12 min",
                    tone: "success",
                  },
                  {
                    icon: <Send className="h-4 w-4" />,
                    title: "47 factures envoyées",
                    description: "Templates FR (28), EN (8), Carole (1), Multi (10)",
                    timestamp: "il y a 2h",
                    tone: "info",
                  },
                  {
                    icon: <FileText className="h-4 w-4" />,
                    title: "Factures générées",
                    description: "Octobre 2025 · 47 PDFs",
                    timestamp: "il y a 3h",
                    tone: "default",
                  },
                  {
                    icon: <CreditCard className="h-4 w-4" />,
                    title: "Liens Stripe créés",
                    description: "47 liens · 12 inclus n-2",
                    timestamp: "hier",
                    tone: "default",
                  },
                  {
                    icon: <AlertTriangle className="h-4 w-4" />,
                    title: "5 familles en retard",
                    description: "À relancer manuellement",
                    timestamp: "hier",
                    tone: "warning",
                  },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* Terminal Log */}
      <Section
        title="🖥️ Terminal Log (jobs longs)"
        subtitle="Composant utilisé pour streaming des logs (extraction, factures, paiements…). Couleurs auto selon emoji/keywords."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <TerminalLog logs={logs} status={progress < 100 ? "running" : "done"} height="400px" />
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Job en cours</CardTitle>
              <CardDescription>Extraction TutorBird</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <div className="mb-1.5 flex justify-between text-xs">
                  <span className="text-muted-foreground">Progression</span>
                  <span className="font-medium tabular-nums">{Math.round(progress)}%</span>
                </div>
                <Progress value={progress} />
              </div>
              <div className="rounded-lg bg-secondary/50 p-3 text-xs">
                <p className="text-muted-foreground">Job ID</p>
                <p className="font-mono text-foreground">a1b2c3d4e5f6</p>
              </div>
              <Button variant="outline" size="sm" className="w-full">
                Voir le log complet
              </Button>
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* EmptyState */}
      <Section title="🌫️ Empty States">
        <div className="grid gap-4 lg:grid-cols-2">
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="Aucune extraction encore"
            description="Lance ta première extraction TutorBird pour voir tes leçons apparaître ici."
            action={<Button variant="accent">Lancer l'extraction</Button>}
          />
          <EmptyState
            icon={<Inbox className="h-6 w-6" />}
            title="Toutes les factures sont envoyées 🎉"
            description="Plus rien à faire pour ce mois-ci. Reviens demain pour suivre les paiements."
          />
        </div>
      </Section>

      {/* Cards mockups divers */}
      <Section title="🎴 Cards diverses (préview pages réelles)">
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Calabresi Aurélie</CardTitle>
                <Badge variant="success">Payé</Badge>
              </div>
              <CardDescription>2 élèves · 18h45 · Octobre 2025</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Montant</span>
                  <span className="font-semibold tabular-nums">315.00 €</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Profs</span>
                  <span>Sophia / Mehdi</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Lien Stripe</span>
                  <span className="font-mono text-xs text-accent">plink_xxx</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Tessier Carole</CardTitle>
                <Badge variant="accent">OCTOPUS SARL</Badge>
              </div>
              <CardDescription>Package · Multi-mois · Monaco</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Montant</span>
                  <span className="font-semibold tabular-nums">1,440.00 €</span>
                </div>
                <Badge variant="warning" className="text-[10px]">
                  Inclut Sept. + Oct. (impayés n-2)
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Aseelah Bin K.</CardTitle>
                <Badge variant="warning">En attente</Badge>
              </div>
              <CardDescription>1 élève · 8h00 · Dubai</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Montant</span>
                  <span className="font-semibold tabular-nums">1,321.80 AED</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Équivalent EUR</span>
                  <span className="font-mono text-xs text-muted-foreground">≈ 334.50 €</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* Footer */}
      <div className="rounded-xl border border-dashed border-border bg-card/50 p-6 text-center">
        <p className="text-sm font-medium text-foreground">
          ✅ Tous les composants sont prêts pour la migration des 12 pages réelles.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Validation visuelle requise avant de commencer l'étape suivante.
        </p>
      </div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-xl font-bold tracking-tight text-foreground">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}
