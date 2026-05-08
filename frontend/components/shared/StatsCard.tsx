"use client";

import { ReactNode } from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "primary" | "accent" | "success" | "warning" | "info" | "violet" | "amber" | "emerald" | "cyan" | "tangerine" | "sky";

const TONE_STYLES: Record<Tone, { bg: string; text: string; ring: string }> = {
  primary:   { bg: "bg-primary/10",   text: "text-primary",   ring: "ring-primary/20" },
  accent:    { bg: "bg-accent/10",    text: "text-accent",    ring: "ring-accent/20" },
  success:   { bg: "bg-success/10",   text: "text-success",   ring: "ring-success/20" },
  warning:   { bg: "bg-warning/10",   text: "text-warning",   ring: "ring-warning/20" },
  info:      { bg: "bg-info/10",      text: "text-info",      ring: "ring-info/20" },
  violet:    { bg: "bg-[#8B5CF6]/10", text: "text-[#8B5CF6]", ring: "ring-[#8B5CF6]/20" },
  amber:     { bg: "bg-[#F59E0B]/10", text: "text-[#F59E0B]", ring: "ring-[#F59E0B]/20" },
  emerald:   { bg: "bg-[#10B981]/10", text: "text-[#10B981]", ring: "ring-[#10B981]/20" },
  cyan:      { bg: "bg-[#06B6D4]/10", text: "text-[#06B6D4]", ring: "ring-[#06B6D4]/20" },
  tangerine: { bg: "bg-[#F97316]/10", text: "text-[#F97316]", ring: "ring-[#F97316]/20" },
  sky:       { bg: "bg-[#3B82F6]/10", text: "text-[#3B82F6]", ring: "ring-[#3B82F6]/20" },
};

interface StatsCardProps {
  label: string;
  value: ReactNode;
  hint?: string;
  /**
   * Optional emphasized footer line (used e.g. to show "Net" amount below the
   * gross total in the À facturer card). Rendered green by default.
   */
  footer?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  trend?: { value: number; positive?: boolean };
  delay?: number;
  className?: string;
}

export function StatsCard({
  label,
  value,
  hint,
  footer,
  icon,
  tone = "primary",
  trend,
  delay = 0,
  className,
}: StatsCardProps) {
  const styles = TONE_STYLES[tone];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
      className={cn(
        "group relative overflow-hidden rounded-xl border border-border bg-card p-5 shadow-[0_1px_3px_rgba(15,27,45,0.04)] transition-shadow hover:shadow-md",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4">
        {icon && (
          <div
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg ring-1 transition-transform group-hover:scale-105",
              styles.bg,
              styles.text,
              styles.ring
            )}
          >
            {icon}
          </div>
        )}
        {trend && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-medium",
              trend.positive
                ? "bg-success/10 text-success"
                : "bg-destructive/10 text-destructive"
            )}
          >
            {trend.positive ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <TrendingDown className="h-3 w-3" />
            )}
            {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      <div className="mt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <div className="mt-1.5 text-2xl font-bold tracking-tight text-foreground">
          {value}
        </div>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        {footer && (
          <div className="mt-3 border-t border-border/60 pt-2 text-sm font-semibold text-success">
            {footer}
          </div>
        )}
      </div>
    </motion.div>
  );
}
