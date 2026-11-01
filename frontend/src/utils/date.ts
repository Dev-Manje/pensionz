// One date format everywhere in the app: "8 Oct 2026" (with ", 16:40" for
// genuine instants) — the month in words can't be misread as dd/MM vs MM/dd.
// A plain "yyyy-MM-dd" date-only string (e.g. a Term's start_date) is parsed
// from its components directly rather than via `new Date()`, since that
// string represents a calendar date, not a UTC instant — running it through
// `new Date()` and reading local getDate()/getMonth() can shift it by a day
// depending on the viewer's timezone offset.
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
// Joined with non-breaking spaces so a date never wraps inside a table cell.
const NBSP = " ";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const dateOnlyMatch = DATE_ONLY.exec(value);
  if (dateOnlyMatch) {
    const [, yyyy, mm, dd] = dateOnlyMatch;
    return `${Number(dd)}${NBSP}${MONTHS[Number(mm) - 1]}${NBSP}${yyyy}`;
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getDate()}${NBSP}${MONTHS[d.getMonth()]}${NBSP}${d.getFullYear()}`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${formatDate(value)}, ${hh}:${min}`;
}

// "just now", "5 min ago", "3 h ago", "yesterday", then the date — for
// feeds like notifications where recency matters more than the exact time.
export function formatRelative(value?: string | null, now: Date = new Date()): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const minutes = Math.floor((now.getTime() - d.getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  if (hours < 48) return "yesterday";
  return formatDate(value);
}

// A local calendar date as yyyy-MM-dd. Not toISOString(): that is UTC, so in
// Malawi (UTC+2) it gives yesterday's date between midnight and 2 a.m.
export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function todayIso(): string {
  return isoDate(new Date());
}
