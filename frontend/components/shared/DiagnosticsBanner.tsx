"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, type ConfigSyncReport, type PhantomTeachersReport } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function DiagnosticsBanner() {
  const [sync, setSync] = useState<ConfigSyncReport | null>(null);
  const [phantoms, setPhantoms] = useState<PhantomTeachersReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        api.get<ConfigSyncReport>("/diagnostics/config-sync"),
        api.get<PhantomTeachersReport>("/diagnostics/phantom-teachers"),
      ]);
      setSync(s);
      setPhantoms(p);
    } catch {
      /* swallow — banner just hides */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  if (dismissed) return null;

  const syncIssues = sync && !sync.all_in_sync;
  const phantomCount = phantoms?.alerts?.length ?? 0;
  const hasIssues = syncIssues || phantomCount > 0;

  if (!sync && !phantoms) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        className={cn(
          "mb-6 overflow-hidden rounded-xl border shadow-sm",
          hasIssues
            ? "border-warning/40 bg-warning/5"
            : "border-success/30 bg-success/5",
        )}
      >
        <div className="flex items-start gap-3 p-4">
          <div
            className={cn(
              "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              hasIssues ? "bg-warning/20 text-warning" : "bg-success/20 text-success",
            )}
          >
            {hasIssues ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          </div>
          <div className="flex-1 space-y-2 text-sm">
            {!hasIssues && (
              <p className="text-foreground">
                <span className="font-medium">Configurations synchronisées.</span>{" "}
                <span className="text-muted-foreground">
                  Drive et local sont alignés. Aucun prof fantôme détecté.
                </span>
              </p>
            )}
            {syncIssues && sync && (
              <div>
                <p className="font-medium text-foreground">⚙️ Désync Drive ↔ local détectée</p>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {Object.entries(sync.files).map(([name, info]) => {
                    if (info.diff.status === "in_sync" || info.diff.status === "missing_both") return null;
                    const local = info.diff.local_count;
                    const drive = info.diff.drive_count;
                    return (
                      <li key={name} className="font-mono">
                        <span className="text-foreground">{name}</span>{" "}
                        {local !== undefined && drive !== undefined && (
                          <span>· local={local} drive={drive}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {phantomCount > 0 && phantoms && (
              <div>
                <p className="font-medium text-foreground">
                  👻 {phantomCount} prof{phantomCount > 1 ? "s" : ""} fantôme(s) détecté(s)
                </p>
                <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                  {phantoms.alerts.map((a) => (
                    <li key={a.teacher}>
                      <span className="font-mono text-foreground">{a.teacher}</span> — {a.tb_unrecorded}{" "}
                      leçons TB Unrecorded ({a.tb_hours} h) chez {a.families.join(", ")}. {a.note}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <Button variant="ghost" size="icon" onClick={refresh} disabled={loading} aria-label="Rafraîchir">
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
            {!hasIssues && (
              <Button variant="ghost" size="icon" onClick={() => setDismissed(true)} aria-label="Fermer">
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
