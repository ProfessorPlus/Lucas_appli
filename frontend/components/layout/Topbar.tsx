"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { ChevronRight, Sun, Moon, CircleDot } from "lucide-react";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

const ROUTE_LABELS: Record<string, string> = {
  "": "Accueil",
  extract: "Extraction",
  twint: "Twint",
  cleanup: "Nettoyage Notion",
  "payment-links": "Liens de paiement",
  invoices: "Factures",
  "send-invoices": "Envoi factures",
  reminders: "Rappels",
  sync: "Synchronisation",
  "update-notion": "Mise à jour Notion",
  settings: "Paramètres",
  teachers: "Professeurs",
  "families-eur": "Familles EUR",
  "special-rates": "Tarifs spéciaux",
  email: "Email",
  drive: "Drive",
  "teachers-payroll": "Récap profs",
  showcase: "Design system",
};

function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const dark = saved === "dark";
    setIsDark(dark);
    document.documentElement.classList.toggle("dark", dark);
  }, []);

  function toggle() {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button
      onClick={toggle}
      className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      aria-label="Basculer thème"
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const crumbs = [{ href: "/", label: "Accueil" }];
  let acc = "";
  for (const seg of segments) {
    acc += `/${seg}`;
    crumbs.push({ href: acc, label: ROUTE_LABELS[seg] ?? seg });
  }

  // Webhook status mock — sera remplacé par un vrai fetch
  const webhookOk = true;

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-8">
      <nav className="flex items-center gap-1.5 text-sm">
        {crumbs.map((c, i) => (
          <span key={c.href} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />}
            {i === crumbs.length - 1 ? (
              <span className="font-medium text-foreground">{c.label}</span>
            ) : (
              <Link
                href={c.href}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                {c.label}
              </Link>
            )}
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <div
          className={cn(
            "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
            webhookOk
              ? "border-success/30 bg-success/10 text-success"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          )}
        >
          <CircleDot className="h-3 w-3" />
          Webhook {webhookOk ? "actif" : "inactif"}
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
