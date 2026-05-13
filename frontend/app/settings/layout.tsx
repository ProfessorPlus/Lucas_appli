"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings, Users, Wallet, Tag, Mail, Database } from "lucide-react";
import { motion } from "framer-motion";

import { PageHeader } from "@/components/shared/PageHeader";
import { DiagnosticsBanner } from "@/components/shared/DiagnosticsBanner";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings/teachers", label: "Professeurs", icon: Users },
  { href: "/settings/families-eur", label: "Familles EUR", icon: Wallet },
  { href: "/settings/special-rates", label: "Tarifs spéciaux", icon: Tag },
  { href: "/settings/email", label: "Email", icon: Mail },
  { href: "/settings/drive", label: "Drive", icon: Database },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <PageHeader
        variant="primary"
        icon={<Settings className="h-6 w-6" />}
        title="Paramètres"
        subtitle="Configure les professeurs, les familles, les tarifs spéciaux et la connexion Drive."
      />

      <DiagnosticsBanner />

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav className="space-y-1">
          {TABS.map((t) => {
            const active = pathname === t.href || pathname.startsWith(t.href + "/");
            const Icon = t.icon;
            return (
              <Link
                key={t.href}
                href={t.href}
                className={cn(
                  "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary/10 font-semibold text-primary"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                )}
              >
                <Icon className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "")} />
                <span>{t.label}</span>
                {active && (
                  <motion.span
                    layoutId="settings-active-dot"
                    className="ml-auto h-1.5 w-1.5 rounded-full bg-accent"
                  />
                )}
              </Link>
            );
          })}
        </nav>

        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
