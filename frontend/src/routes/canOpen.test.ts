import { describe, expect, it } from "vitest";
import { canOpen } from "./RoleRouter";

describe("canOpen", () => {
  it("sends a principal officer home instead of to a staff page left over from another session", () => {
    expect(canOpen("/contributions?fund=1", ["principal_officer"])).toBe(false);
    expect(canOpen("/approvals/123", ["principal_officer"])).toBe(false);
    expect(canOpen("/po/schemes/abc?tab=members", ["principal_officer"])).toBe(true);
  });

  it("lets staff back to the page they were on, and everyone to their inbox and account", () => {
    expect(canOpen("/contributions?fund=1", ["contributions_officer"])).toBe(true);
    expect(canOpen("/po", ["contributions_officer"])).toBe(false);
    expect(canOpen("/notifications", ["principal_officer"])).toBe(true);
    expect(canOpen("/account/password", ["member"])).toBe(true);
    expect(canOpen("/", ["member"])).toBe(true);
  });
});
