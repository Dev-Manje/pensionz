import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import { TableStateRow } from "./TableStateRow";

function renderRow(props: Partial<Parameters<typeof TableStateRow>[0]>) {
  return render(
    <Table>
      <TableBody>
        <TableStateRow colSpan={3} count={0} empty="No banks yet." {...props} />
      </TableBody>
    </Table>,
  );
}

describe("TableStateRow", () => {
  afterEach(cleanup);

  it("shows progress while the first load is running", () => {
    renderRow({ loading: true });
    expect(screen.getByLabelText("Loading")).toBeTruthy();
    expect(screen.queryByText("No banks yet.")).toBeNull();
  });

  it("explains an empty table", () => {
    renderRow({});
    expect(screen.getByText("No banks yet.")).toBeTruthy();
  });

  it("shows a failed load with Retry", () => {
    const retry = vi.fn();
    renderRow({ error: "Network error", onRetry: retry });
    expect(screen.getByText("Network error")).toBeTruthy();
    screen.getByText("Retry").click();
    expect(retry).toHaveBeenCalledOnce();
  });

  it("renders nothing when there are rows", () => {
    const { container } = renderRow({ count: 2 });
    expect(container.querySelector("tbody")?.children.length).toBe(0);
  });

  it("still shows an error above existing rows", () => {
    renderRow({ count: 2, error: "Couldn't refresh" });
    expect(screen.getByText("Couldn't refresh")).toBeTruthy();
  });
});
