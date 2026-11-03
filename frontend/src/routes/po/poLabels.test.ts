import { describe, expect, it } from "vitest";
import { dueText, isLate, recentMonths } from "./poLabels";

describe("dueText", () => {
  it("counts days to the due date and past it", () => {
    expect(dueText(12)).toBe("due in 12 days");
    expect(dueText(1)).toBe("due in 1 day");
    expect(dueText(0)).toBe("due today");
    expect(dueText(-1)).toBe("1 day overdue");
    expect(dueText(-6)).toBe("6 days overdue");
  });
});

describe("isLate", () => {
  it("is late only when past due and members aren't credited yet", () => {
    expect(isLate("not_started", -1)).toBe(true);
    expect(isLate("awaiting_allocation", -3)).toBe(true);
    expect(isLate("allocated", -3)).toBe(false);
    expect(isLate("draft", 0)).toBe(false);
  });
});

describe("recentMonths", () => {
  it("lists this month back a year, across the year end", () => {
    const months = recentMonths(new Date(2026, 0, 15));
    expect(months).toHaveLength(13);
    expect(months.slice(0, 3)).toEqual(["2026-01-01", "2025-12-01", "2025-11-01"]);
    expect(months[12]).toBe("2025-01-01");
  });
});
