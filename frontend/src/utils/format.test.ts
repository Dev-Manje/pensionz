import { describe, expect, it } from "vitest";
import { formatAmount, formatMoney, formatPhone, formatPrice, formatRate, formatUnits, formatWhole } from "./format";
import { formatDate, formatDateTime, isoDate } from "./date";

// The non-breaking space the formatters use so values never wrap mid-way.
const nb = (s: string) => s.replace(/ /g, " ");

describe("formatMoney", () => {
  it("shows the currency, thousands separators and two decimals", () => {
    expect(formatMoney(1250000)).toBe(nb("MWK 1,250,000.00"));
    expect(formatMoney(133241.1)).toBe(nb("MWK 133,241.10"));
    expect(formatMoney(-17753.42)).toBe(nb("MWK -17,753.42"));
  });
  it("accepts numeric strings and another currency", () => {
    expect(formatMoney("5000")).toBe(nb("MWK 5,000.00"));
    expect(formatMoney(10, "USD")).toBe(nb("USD 10.00"));
  });
  it("shows a dash when there is no figure", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("")).toBe("—");
    expect(formatMoney("abc")).toBe("—");
  });
});

describe("formatAmount / formatWhole", () => {
  it("formats without the currency", () => {
    expect(formatAmount(0)).toBe("0.00");
    expect(formatAmount(1234.5)).toBe("1,234.50");
    expect(formatWhole(1234567.89)).toBe("1,234,568");
  });
});

describe("formatRate", () => {
  it("is per annum with two to four decimals", () => {
    expect(formatRate(12.5)).toBe("12.50% p.a.");
    expect(formatRate(12.125)).toBe("12.125% p.a.");
    expect(formatRate(12.12345)).toBe("12.1235% p.a.");
  });
  it("can drop p.a. for fees and tax", () => {
    expect(formatRate(20, { perAnnum: false })).toBe("20.00%");
  });
  it("shows a dash when missing", () => {
    expect(formatRate(undefined)).toBe("—");
  });
});

describe("formatPhone", () => {
  it("groups Malawi numbers", () => {
    expect(formatPhone("0999123456")).toBe("0999 123 456");
    expect(formatPhone("+265999123456")).toBe("+265 999 123 456");
    expect(formatPhone("00265 888 12 34 56")).toBe("+265 888 123 456");
  });
  it("leaves other numbers as typed", () => {
    expect(formatPhone(" +44 20 7946 0000 ")).toBe("+44 20 7946 0000");
    expect(formatPhone("12345")).toBe("12345");
  });
  it("shows a dash when empty", () => {
    expect(formatPhone("")).toBe("—");
    expect(formatPhone(null)).toBe("—");
  });
});

describe("formatDate", () => {
  it("reads day month-in-words year", () => {
    expect(formatDate("2026-10-02")).toBe(nb("2 Oct 2026"));
    expect(formatDate("2026-01-31")).toBe(nb("31 Jan 2026"));
  });
  it("never shifts a calendar date by time zone", () => {
    expect(formatDate("2026-12-31")).toBe(nb("31 Dec 2026"));
  });
  it("reads instants in local (Malawi) time", () => {
    // 22:30 UTC on 2 Oct is 00:30 on 3 Oct in Malawi (UTC+2)
    expect(formatDate("2026-10-02T22:30:00Z")).toBe(nb("3 Oct 2026"));
    expect(formatDateTime("2026-10-02T22:30:00Z")).toBe(`${nb("3 Oct 2026")}, 00:30`);
  });
  it("shows a dash for missing or bad values", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("garbage")).toBe("—");
  });
});

describe("isoDate", () => {
  it("uses the local calendar date, not UTC", () => {
    // 01:00 in Malawi on 3 Oct is still 2 Oct in UTC
    expect(isoDate(new Date("2026-10-02T23:00:00Z"))).toBe("2026-10-03");
  });
});

describe("formatUnits / formatPrice", () => {
  it("keeps six decimals for units and unit prices", () => {
    expect(formatUnits(12150.000996)).toBe("12,150.000996");
    expect(formatPrice("12.345678")).toBe("12.345678");
    expect(formatUnits(null)).toBe("—");
  });
});
