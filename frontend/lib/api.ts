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

// ── Settings ─────────────────────────────────────────────────────────────

export interface Teacher {
  name: string;
  connect_account_id: string;
  pay_rate_chf: number;
  pay_rate_eur: number;
  auto_chf: boolean;
}

export interface TeacherInput {
  name: string;
  connect_account_id?: string;
  pay_rate_chf?: number;
  pay_rate_eur?: number;
  auto_chf?: boolean;
}

export interface TeacherStripeStatus {
  name: string;
  account_id: string;
  status:
    | "active"
    | "pending"
    | "incomplete"
    | "unconfigured"
    | "error"
    | "no_stripe_key"
    | "stripe_not_installed";
  charges_enabled?: boolean;
  payouts_enabled?: boolean;
  details_submitted?: boolean;
  error?: string;
}

export interface SpecialRate {
  id: string;
  teacher: string;
  parent: string;
  student: string;
  pay_rate: number;
  currency: string;
}

export interface SpecialRateInput {
  teacher: string;
  parent: string;
  pay_rate: number;
  currency?: string;
  student?: string;
}

export interface EmailConfig {
  email: string;
  app_password_set: boolean;
  app_password_preview: string;
}

export interface DriveTestResult {
  ok: boolean;
  root_id?: string;
  config_folder_id?: string;
  files?: Array<{ id: string; name: string; size?: string; modifiedTime: string }>;
  error?: string;
}

export interface DriveWriteTestResult {
  ok: boolean;
  test_target?: string;
  drive_id?: string;
  new_modified_time?: string;
  note?: string;
  error?: string;
}

// ── Diagnostics ──────────────────────────────────────────────────────────

export interface ConfigSyncFile {
  filename: string;
  local_exists: boolean;
  local_size: number;
  drive_exists: boolean;
  drive_id: string | null;
  drive_modified_time: string | null;
  diff: {
    status: "in_sync" | "diverged" | "missing_both" | "error";
    only_local?: string[] | string[][];
    only_drive?: string[] | string[][];
    changed?: string[][];
    local_count?: number;
    drive_count?: number;
    masked_diff?: Record<string, unknown>;
    error?: string;
  };
}

export interface ConfigSyncReport {
  all_in_sync: boolean;
  files: Record<string, ConfigSyncFile>;
}

export interface PhantomTeacherAlert {
  severity: "high" | "medium" | "low";
  teacher: string;
  tb_lessons: number;
  tb_hours: number;
  tb_unrecorded: number;
  families: string[];
  note: string;
}

export interface PhantomTeachersReport {
  alerts: PhantomTeacherAlert[];
  tb_teacher_count?: number;
  note?: string;
}

// ── Dashboard ────────────────────────────────────────────────────────────

export interface DashboardSummary {
  nb_profs: number;
  nb_profs_breakdown: { tutorbird_or_secrets: number; notion_only: number };
  nb_families: number;
  amounts_by_currency: Record<string, number>;
  ca_total_eur: number;
  profs_total_eur: number;
  net_eur: number;
  extraction_end: string | null;
}

export interface InvoiceFolder {
  id: string;
  month: string;
  year?: string | number;
  source?: string;
}

export interface DashboardPayments {
  folder: string;
  target_month: string | null;
  total: number;
  paid: number;
  unpaid: number;
  pct: number;
  amounts_by_currency_paid: Record<string, number>;
  amounts_by_currency_due: Record<string, number>;
  error?: string;
}

export interface DashboardEmails {
  invoice_sent_date: string | null;
  reminder_sent_date: string | null;
  reminder_count: number;
  error?: string;
}

export interface RandomQuotes {
  hadith: { text: string; source: string; narrator: string };
  quote: { text: string; author: string };
}

// ── Payment Links ────────────────────────────────────────────────────────

export interface ExtractedFamily {
  family_id: string;
  parent_name: string;
  currency: string;
  lessons: number;
}

export interface PaymentLinksList {
  exists: boolean;
  source?: string;
  count: number;
  links: Array<{
    family_id?: string;
    parent_name?: string;
    amount?: number;
    currency?: string;
    payment_link?: string;
    stripe_payment_link_id?: string;
    includes_previous_months?: string;
    previous_amount?: number;
    metadata?: Record<string, unknown>;
  }>;
}

export interface UnpaidN2Family {
  parent_name: string;
  total_amount: number;
  currency: string;
}

export interface UnpaidN2Response {
  success: boolean;
  families: Record<string, UnpaidN2Family>;
  month_label?: string;
  total_rows?: number;
  error?: string | null;
}

export interface CreateLinksBody {
  no_split: boolean;
  selected_teachers?: string[] | null;
  payment_method_types?: string[] | null;
  target_family_ids?: string[] | null;
  additional_amounts?: Record<string, unknown> | null;
  skip_if_exists: boolean;
}
