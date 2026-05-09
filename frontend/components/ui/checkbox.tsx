"use client";

import * as React from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CheckboxProps {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function Checkbox({
  checked = false,
  onCheckedChange,
  disabled,
  id,
  className,
}: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      id={id}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "peer flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
        checked
          ? "border-accent bg-accent text-accent-foreground"
          : "border-border bg-card hover:border-accent/40",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      {checked && <Check className="h-3 w-3" strokeWidth={3} />}
    </button>
  );
}
