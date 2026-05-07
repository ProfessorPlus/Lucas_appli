"use client";

import { Check, Circle } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface WorkflowStep {
  label: string;
  description?: string;
  status: "done" | "active" | "pending";
}

interface WorkflowStepperProps {
  steps: WorkflowStep[];
  className?: string;
}

export function WorkflowStepper({ steps, className }: WorkflowStepperProps) {
  return (
    <ol className={cn("space-y-0", className)}>
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        return (
          <li key={i} className="flex gap-4">
            {/* Indicator + connector */}
            <div className="flex flex-col items-center">
              <motion.div
                initial={{ scale: 0.85, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: i * 0.05 }}
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold transition-colors",
                  step.status === "done" && "border-success bg-success text-white",
                  step.status === "active" &&
                    "border-accent bg-accent/10 text-accent shadow-md shadow-accent/20",
                  step.status === "pending" && "border-border bg-card text-muted-foreground"
                )}
              >
                {step.status === "done" ? (
                  <Check className="h-4 w-4" strokeWidth={3} />
                ) : step.status === "active" ? (
                  <Circle className="h-2.5 w-2.5 fill-accent text-accent" />
                ) : (
                  <span>{i + 1}</span>
                )}
              </motion.div>
              {!isLast && (
                <div
                  className={cn(
                    "mt-1 h-12 w-0.5",
                    step.status === "done" ? "bg-success" : "bg-border"
                  )}
                />
              )}
            </div>

            {/* Content */}
            <div className={cn("flex-1 pb-8", isLast && "pb-0")}>
              <p
                className={cn(
                  "text-sm font-semibold",
                  step.status === "active" ? "text-foreground" : "text-foreground"
                )}
              >
                {step.label}
              </p>
              {step.description && (
                <p className="mt-0.5 text-xs text-muted-foreground">{step.description}</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
