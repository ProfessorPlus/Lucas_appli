import { cn } from "@/lib/utils";

const CURRENCY_BADGE: Record<string, { label: string; className: string }> = {
  EUR: { label: "EUR", className: "bg-primary/10 text-primary" },
  CHF: { label: "CHF", className: "bg-[#3B82F6]/10 text-[#3B82F6]" },
  AED: { label: "AED", className: "bg-[#F59E0B]/10 text-[#F59E0B]" },
  USD: { label: "USD", className: "bg-[#10B981]/10 text-[#10B981]" },
};

interface MultiCurrencyTotalProps {
  amounts: Record<string, number>;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function MultiCurrencyTotal({
  amounts,
  size = "md",
  className,
}: MultiCurrencyTotalProps) {
  const entries = Object.entries(amounts).filter(([, v]) => Math.abs(v) > 0.001);

  if (entries.length === 0) {
    return (
      <span className={cn("text-muted-foreground", className)}>—</span>
    );
  }

  const sizeStyles = {
    sm: "text-sm gap-1.5",
    md: "text-base gap-2",
    lg: "text-2xl gap-3 font-bold",
  }[size];

  return (
    <div className={cn("flex flex-wrap items-baseline", sizeStyles, className)}>
      {entries.map(([currency, value], i) => {
        const badge = CURRENCY_BADGE[currency.toUpperCase()] ?? {
          label: currency.toUpperCase(),
          className: "bg-secondary text-foreground",
        };
        return (
          <span key={currency} className="inline-flex items-baseline gap-1">
            {i > 0 && <span className="text-muted-foreground/50">+</span>}
            <span className="font-semibold tabular-nums">
              {new Intl.NumberFormat("fr-FR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              }).format(value)}
            </span>
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[0.65em] font-bold uppercase tracking-wide",
                badge.className
              )}
            >
              {badge.label}
            </span>
          </span>
        );
      })}
    </div>
  );
}
