import { formatMoney, formatRate } from "../../../../utils/format";
import type { RateType } from "../../../../api/types";

// "5.00%" / "MWK 2,500.00 a month" / "Balance of cost" (DB employer)
export function rateLabel(type: RateType, rate: string | null): string {
  if (rate === null) return "Balance of cost";
  return type === "percent" ? formatRate(rate, { perAnnum: false }) : `${formatMoney(rate)} a month`;
}

export function vestedLabel(pct: string): string {
  return `${Number(pct)}% vested`;
}
