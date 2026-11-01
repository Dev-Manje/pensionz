import { describe, expect, it } from "vitest";
import { describeDetail } from "./client";

describe("describeDetail", () => {
  it("passes a plain message through", () => {
    expect(describeDetail("Account is not active")).toBe("Account is not active");
  });
  it("joins FastAPI validation messages instead of showing [object Object]", () => {
    expect(
      describeDetail([
        { loc: ["body", "amount"], msg: "Input should be greater than 0" },
        { loc: ["body", "tenor_days"], msg: "Field required" },
      ]),
    ).toBe("Input should be greater than 0; Field required");
  });
  it("gives up on shapes it doesn't know", () => {
    expect(describeDetail({ weird: true })).toBeNull();
    expect(describeDetail(undefined)).toBeNull();
  });
});
