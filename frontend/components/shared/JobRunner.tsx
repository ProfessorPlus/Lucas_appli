"use client";

/**
 * Universal fire-and-poll runner. Subscribes to SSE for live updates AND
 * polls every 2s as a fallback. Shows a TerminalLog with progress bar.
 *
 * Use it for any long-running endpoint (extract, invoices, payment_links, ...).
 */

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { toast } from "sonner";

import { api, type Job } from "@/lib/api";
import { TerminalLog } from "./TerminalLog";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";

export interface JobRunnerProps<TResult> {
  jobId: string;
  onDone?: (result: TResult) => void;
  onError?: (error: string) => void;
  onCancel?: () => void;
  height?: string;
}

export function JobRunner<TResult = unknown>({
  jobId,
  onDone,
  onError,
  onCancel,
  height = "360px",
}: JobRunnerProps<TResult>) {
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<Job["status"]>("pending");
  const finishedRef = useRef(false);

  // Initial fetch + 2s polling fallback (works even when SSE is blocked).
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const job = await api.get<Job<TResult>>(`/jobs/${jobId}`);
        if (cancelled) return;
        setLogs(job.logs);
        setProgress(job.progress * 100);
        setStatus(job.status);
        if ((job.status === "done" || job.status === "error") && !finishedRef.current) {
          finishedRef.current = true;
          if (job.status === "done") {
            onDone?.(job.result as TResult);
          } else {
            onError?.(job.error || "Erreur inconnue");
            toast.error(`Job échoué : ${job.error || "erreur inconnue"}`);
          }
        }
      } catch (err) {
        // network glitch — keep polling silently
      }
    }

    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, onDone, onError]);

  // SSE stream — gives instant updates between polls.
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const url = `/api/backend/jobs/${jobId}/stream`;
    const source = new EventSource(url);

    source.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        if (payload.type === "log") {
          setLogs((prev) => [...prev, payload.message as string]);
        } else if (payload.type === "progress") {
          setProgress(payload.value * 100);
        } else if (payload.type === "status") {
          setStatus(payload.status as Job["status"]);
        }
      } catch {
        /* ignore malformed payloads */
      }
    };
    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [jobId]);

  const isRunning = status === "running" || status === "pending";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          {isRunning && <Loader2 className="h-4 w-4 animate-spin text-accent" />}
          <span className="font-medium text-foreground">
            {status === "pending" && "En attente…"}
            {status === "running" && "Extraction en cours…"}
            {status === "done" && "✅ Terminé"}
            {status === "error" && "❌ Erreur"}
          </span>
          <span className="font-mono text-xs text-muted-foreground">
            · job <span className="text-foreground">{jobId}</span>
          </span>
        </div>
        {onCancel && (
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isRunning}>
            <X /> Fermer
          </Button>
        )}
      </div>
      <Progress value={progress} />
      <TerminalLog logs={logs} status={status === "pending" ? "running" : status} height={height} />
    </div>
  );
}
