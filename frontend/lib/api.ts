/**
 * Tiny typed fetch wrapper. All calls go through `/api/backend/*` (rewritten
 * by next.config.js to the actual FastAPI URL) so this module never needs
 * absolute URLs in client code.
 */

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "change-me";

class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, payload: unknown, message: string) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(`/api/backend${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!res.ok) {
    const detail =
      (parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : null) ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, parsed, detail);
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  apiKey: API_KEY,
};

export { ApiError };

// ── Domain types shared with the backend ─────────────────────────────────

export type JobStatus = "pending" | "running" | "done" | "error";

export interface Job<TResult = unknown> {
  id: string;
  name: string;
  status: JobStatus;
  progress: number; // 0..1
  logs: string[];
  result: TResult | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

export interface ExtractRequest {
  start_date: string;
  end_date: string;
  start_time?: string;
  end_time?: string;
  notion_prof_page_ids?: string[] | null;
}

export interface ExtractSummary {
  families: number;
  lessons: number;
  notion_added: number;
  amounts_by_currency: Record<string, number>;
  ca_total_eur: number;
  profs_total_eur: number;
  net_eur: number;
  fx?: { chf_eur: number | null; aed_eur: number | null };
  details_by_family: Array<{
    family_id: string;
    parent_name: string;
    is_euro: boolean;
    EUR: number;
    CHF: number;
    AED: number;
  }>;
  extraction_end: string;
}

export interface NotionProfEntry {
  page_id: string;
  famille: string;
  professeur: string;
  eleve: string;
  devise_client: string;
  taux_horaire_client: number;
  taux_horaire_prof: number;
  devise_prof: string;
  heures_faites: number;
  email_client: string;
  email_prof: string;
  language: string;
}

export interface NotionProfsResponse {
  success: boolean;
  entries: NotionProfEntry[];
  error: string | null;
}
