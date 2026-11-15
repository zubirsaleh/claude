import "server-only";

const API = process.env.TSCH_API_INTERNAL_URL ?? "http://localhost:8000";

export type Connection = {
  name: string; mode: string | null; status: string; detail: string;
  last_heartbeat_utc: string | null;
};
export type Modes = {
  default_mode: string; executable_modes: string[]; live_execution_available: boolean;
  notes: Record<string, string>;
};
export type Account = {
  id: string; mode: string; broker: string; server: string; login_masked: string;
  account_type: string; currency: string; label: string;
};
export type Strategy = {
  id: string; key: string; version: string; name: string; description: string;
  implemented: boolean;
};
export type Order = {
  id: string; mode: string; state: string; symbol: string; side: string; volume: string;
  sl: string | null; tp: string | null; est_loss_at_stop: string | null;
  est_risk_pct: string | null; risk_reasons: string[]; created_utc: string;
  outcome: string | null;
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

export async function get<T>(path: string): Promise<Result<T>> {
  try {
    const r = await fetch(`${API}${path}`, { cache: "no-store" });
    if (!r.ok) return { ok: false, error: `HTTP ${r.status}` };
    return { ok: true, data: (await r.json()) as T };
  } catch {
    return { ok: false, error: "API unreachable" };
  }
}
