"use client";

import { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface TimelineItem {
  icon: ReactNode;
  title: string;
  description?: string;
  timestamp: string;
  tone?: "default" | "success" | "warning" | "info";
}

const TONE_STYLES = {
  default: "bg-secondary text-foreground",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  info: "bg-info/10 text-info",
};

interface ActivityTimelineProps {
  items: TimelineItem[];
  className?: string;
}

export function ActivityTimeline({ items, className }: ActivityTimelineProps) {
  return (
    <ul className={cn("space-y-3", className)}>
      {items.map((item, i) => (
        <motion.li
          key={i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.04 }}
          className="flex items-start gap-3"
        >
          <div
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              TONE_STYLES[item.tone ?? "default"]
            )}
          >
            {item.icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
              <span className="shrink-0 text-xs text-muted-foreground">
                {item.timestamp}
              </span>
            </div>
            {item.description && (
              <p className="text-xs text-muted-foreground">{item.description}</p>
            )}
          </div>
        </motion.li>
      ))}
    </ul>
  );
}
