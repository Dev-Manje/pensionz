// Shared number formatting — one look for money, rates and phone numbers
// everywhere: MWK 1,250,000.00 · 8.00% · 12,150.000996 units · 0999 123 456.
// Always en-US grouping (comma thousands, dot decimals) rather than the
// browser's locale, so a figure reads the same on every device and matches
// the PDFs and statements.

const TWO_DP = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
// Units and unit prices are held to 6 decimals (pz-pension-domain).
const SIX_DP = new Intl.NumberFormat("en-US", { minimumFractionDigits: 6, maximumFractionDigits: 6 });
// Rates keep up to 4 decimals (a 12.125% tier must not show as 12.13%).
const RATE = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });

type Num = number | string | null | undefined;

function toNumber(value: Num): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** "MWK 1,250,000.00" — "—" when there's no figure. */
export function formatMoney(value: Num, currency = "MWK"): string {
  const n = toNumber(value);
  // non-breaking space: "MWK" never ends up on a line of its own
  return n === null ? "—" : `${currency} ${TWO_DP.format(n)}`;
}

/** "1,250,000.00" — for table columns whose heading already says the currency. */
export function formatAmount(value: Num): string {
  const n = toNumber(value);
  return n === null ? "—" : TWO_DP.format(n);
}

/** "12,150.000996" — fund units. */
export function formatUnits(value: Num): string {
  const n = toNumber(value);
  return n === null ? "—" : SIX_DP.format(n);
}

/** "12.345678" — unit price. */
export function formatPrice(value: Num): string {
  const n = toNumber(value);
  return n === null ? "—" : SIX_DP.format(n);
}

/** "1,250,000" — chart axes and other places where pennies are noise. */
export function formatWhole(value: Num): string {
  const n = toNumber(value);
  return n === null ? "—" : WHOLE.format(n);
}

/** "12.50% p.a." — or "12.50%" with `perAnnum: false` (fee and tax percentages). */
export function formatRate(value: Num, { perAnnum = true }: { perAnnum?: boolean } = {}): string {
  const n = toNumber(value);
  return n === null ? "—" : `${RATE.format(n)}%${perAnnum ? " p.a." : ""}`;
}

/**
 * Malawi numbers grouped for reading: "0999 123 456" or "+265 999 123 456".
 * Anything that doesn't look like a Malawi number is shown as typed.
 */
export function formatPhone(value?: string | null): string {
  if (!value) return "—";
  const digits = value.replace(/[^\d+]/g, "");
  let m = /^0(\d{3})(\d{3})(\d{3})$/.exec(digits);
  if (m) return `0${m[1]} ${m[2]} ${m[3]}`;
  m = /^(?:\+|00)265(\d{3})(\d{3})(\d{3})$/.exec(digits);
  if (m) return `+265 ${m[1]} ${m[2]} ${m[3]}`;
  return value.trim();
}

/** Table-cell style for figures: right-aligned by the caller, digits lined up. */
export const numberCell = { fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" } as const;
