"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

interface TerminalLogProps {
  logs: string[];
  height?: string;
  showStatusDot?: boolean;
  status?: "running" | "done" | "error" | "idle";
  className?: string;
}

const STATUS_COLOR = {
  running: "bg-warning",
  done: "bg-success",
  error: "bg-destructive",
  idle: "bg-muted-foreground/40",
};

export function TerminalLog({
  logs,
  height = "320px",
  showStatusDot = true,
  status = "idle",
  className,
}: TerminalLogProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-[#0D1117] shadow-inner",
        className
      )}
    >
      {/* Header chrome */}
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-2">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#FF5F57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#FEBC2E]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28C840]" />
        </div>
        <div className="flex items-center gap-2 text-xs text-white/50">
          {showStatusDot && (
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                STATUS_COLOR[status],
                status === "running" && "animate-pulse"
              )}
            />
          )}
          <span className="font-mono uppercase tracking-wider">{status}</span>
        </div>
      </div>

      {/* Logs */}
      <div
        ref={ref}
        style={{ height }}
        className="scrollbar-thin overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed"
      >
        {logs.length === 0 ? (
          <p className="text-white/30">En attente de logs…</p>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="flex gap-3">
              <span className="shrink-0 text-white/30 tabular-nums">
                {String(i + 1).padStart(3, "0")}
              </span>
              <span className={lineColor(line)}>{line}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function lineColor(line: string): string {
  if (/❌|error|fail/i.test(line)) return "text-[#F87171]";
  if (/⚠️|warning/i.test(line)) return "text-[#FBBF24]";
  if (/✅|success|done|terminé/i.test(line)) return "text-[#34D399]";
  if (/🔍|debug|info/i.test(line)) return "text-[#60A5FA]";
  if (/➜|🚀/.test(line)) return "text-[#A78BFA]";
  return "text-white/85";
}
