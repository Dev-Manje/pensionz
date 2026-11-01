import { describe, expect, it } from "vitest";
import { statusLabel, statusTone } from "./labels";

describe("statusLabel", () => {
  it("uses the shared wording", () => {
    expect(statusLabel("pending")).toBe("Awaiting approval");
    expect(statusLabel("cancelled")).toBe("Withdrawn");
  });

  it("turns unknown codes into readable words, never raw snake_case", () => {
    expect(statusLabel("paid_up")).toBe("Paid up");
  });

  it("shows a dash when there is no status", () => {
    expect(statusLabel(null)).toBe("—");
  });
});

describe("statusTone", () => {
  it("colours outcomes", () => {
    expect(statusTone("approved")).toBe("success");
    expect(statusTone("rejected")).toBe("error");
    expect(statusTone("something_new")).toBe("default");
  });
});
