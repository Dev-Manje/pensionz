import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { DiffView } from "./DiffView";

describe("DiffView", () => {
  afterEach(cleanup);

  it("lists only the fields that change when given the current values", () => {
    render(
      <DiffView
        before={{ name: "Old Fund", code: "F1", trustees: [{ id: "1", full_name: "Ann" }] }}
        after={{ name: "New Fund", code: "F1", trustees: [{ id: "1", full_name: "Ann" }] }}
      />,
    );
    expect(screen.getByText("Name")).toBeTruthy();
    expect(screen.getByText("New Fund")).toBeTruthy();
    expect(screen.queryByText("Code")).toBeNull();
    expect(screen.queryByText("Trustees")).toBeNull();
  });

  it("leaves out blank values when proposing a new record", () => {
    render(<DiffView after={{ name: "New Fund", fax: null, trustees: [] }} />);
    expect(screen.getByText("Name")).toBeTruthy();
    expect(screen.queryByText("Fax")).toBeNull();
    expect(screen.queryByText("Trustees")).toBeNull();
  });
});
