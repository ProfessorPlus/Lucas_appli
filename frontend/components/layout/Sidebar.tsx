"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Users,
  Download,
  Zap,
  Trash2,
  CreditCard,
  FileText,
  Mail,
  Bell,
  RefreshCw,
  Upload,
  Settings,
  GraduationCap,
  Sparkles,
  Palette,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const SECTIONS: NavSection[] = [
  {
    label: "Actions",
    items: [
      { label: "Accueil", href: "/", icon: Home },
      { label: "Professeurs", href: "/teachers-payroll", icon: Users },
    ],
  },
  {
    label: "Extraction",
    items: [
      { label: "Extraire les leçons", href: "/extract", icon: Download },
      { label: "Activer Twint", href: "/twint", icon: Zap },
      { label: "Nettoyage Notion", href: "/cleanup", icon: Trash2 },
    ],
  },
  {
    label: "Paiements & Factures",
    items: [
      { label: "Liens de paiement", href: "/payment-links", icon: CreditCard },
      { label: "Générer factures", href: "/invoices", icon: FileText },
      { label: "Éditer une facture", href: "/edit-invoice", icon: Palette },
    ],
  },
  {
    label: "Communication",
    items: [
      { label: "Envoyer factures", href: "/send-invoices", icon: Mail },
      { label: "Rappels paiement", href: "/reminders", icon: Bell },
    ],
  },
  {
    label: "Synchronisation",
    items: [
      { label: "Sync Stripe → Notion", href: "/sync", icon: RefreshCw },
      { label: "Ajouter lignes Notion", href: "/update-notion", icon: Upload },
    ],
  },
  {
    label: "Configuration",
    items: [{ label: "Paramètres", href: "/settings", icon: Settings }],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-[280px] flex-col self-start bg-sidebar-gradient text-sidebar-foreground md:flex">
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-sidebar-border/60 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-gradient text-white shadow-lg shadow-accent/20">
          <GraduationCap className="h-5 w-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-base font-bold leading-none text-white">
            Professor<span className="text-accent">+</span>
          </span>
          <span className="text-xs text-sidebar-foreground/50">Admin</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin px-3 py-5">
        {SECTIONS.map((section) => (
          <div key={section.label} className="mb-6">
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-sidebar-foreground/40">
              {section.label}
            </p>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active =
                  pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all",
                        active
                          ? "bg-sidebar-accent text-white shadow-sm"
                          : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-white"
                      )}
                    >
                      <Icon
                        className={cn(
                          "h-4 w-4 shrink-0 transition-colors",
                          active
                            ? "text-accent"
                            : "text-sidebar-foreground/50 group-hover:text-accent"
                        )}
                      />
                      <span className="truncate">{item.label}</span>
                      {active && (
                        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent shadow-sm shadow-accent/50" />
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}

        {/* Showcase link (dev) */}
        <div className="border-t border-sidebar-border/60 pt-4">
          <Link
            href="/showcase"
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all",
              pathname === "/showcase"
                ? "bg-sidebar-accent text-white"
                : "text-sidebar-foreground/60 hover:bg-sidebar-accent/40 hover:text-white"
            )}
          >
            <Sparkles className="h-4 w-4 text-accent" />
            <span>Design system</span>
          </Link>
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border/60 px-6 py-4">
        <p className="text-[10px] uppercase tracking-wide text-sidebar-foreground/40">
          Dernier dossier
        </p>
        <p className="mt-1 flex items-center gap-1.5 text-sm font-medium text-emerald">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald" />
          Octobre 2025 · 28-10
        </p>
      </div>
    </aside>
  );
}
