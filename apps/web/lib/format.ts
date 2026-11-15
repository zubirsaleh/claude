export type Mode = "SIM" | "MT5_DEMO" | "TRADINGVIEW_PAPER_MANUAL" | "LIVE_DISABLED";

export const MODE_LABEL: Record<Mode, string> = {
  SIM: "Internal SIM · synthetic prices",
  MT5_DEMO: "MT5 DEMO",
  TRADINGVIEW_PAPER_MANUAL: "TradingView Paper · MANUAL",
  LIVE_DISABLED: "LIVE DISABLED",
};

/** Show a money/number value or N/A. Never invents a value for missing data. */
export function fmtNum(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || v === "") return "N/A";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "N/A";
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Quantity without storage padding: "0.0100000000" -> "0.01". */
export function fmtQty(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "N/A";
  if (!/^-?\d+(\.\d+)?$/.test(v)) return "N/A";
  return v.includes(".") ? v.replace(/0+$/, "").replace(/\.$/, "") : v;
}

/** Render a UTC timestamp in the operator's display zone (default Asia/Kuala_Lumpur). */
export function fmtTime(iso: string | null | undefined, timeZone = "Asia/Kuala_Lumpur"): string {
  if (!iso) return "N/A";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "N/A";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone, year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZoneName: "short",
  }).format(d);
}

export function statusTone(status: string): "ok" | "warn" | "off" {
  if (status === "CONNECTED") return "ok";
  if (status === "MANUAL ONLY") return "warn";
  return "off";
}
