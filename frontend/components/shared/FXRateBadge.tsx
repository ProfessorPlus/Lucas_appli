import { Activity } from "lucide-react";
import { cn } from "@/lib/utils";

interface FXRateBadgeProps {
  pair: string; // ex: "CHF→EUR"
  rate: number;
  source: "frankfurter" | "ecb" | "hardcoded";
  className?: string;
}

const SOURCE_LABEL: Record<FXRateBadgeProps["source"], { label: string; tone: string }> = {
  frankfurter: { label: "Frankfurter", tone: "text-success" },
  ecb: { label: "ECB", tone: "text-info" },
  hardcoded: { label: "fallback", tone: "text-warning" },
};

export function FXRateBadge({ pair, rate, source, className }: FXRateBadgeProps) {
  const meta = SOURCE_LABEL[source];
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs",
        className
      )}
    >
      <Activity className={cn("h-3 w-3", meta.tone)} />
      <span className="font-medium tabular-nums text-foreground">
        {pair} = {rate.toFixed(4)}
      </span>
      <span className="text-muted-foreground">·</span>
      <span className={cn("font-medium", meta.tone)}>{meta.label}</span>
    </div>
  );
}
