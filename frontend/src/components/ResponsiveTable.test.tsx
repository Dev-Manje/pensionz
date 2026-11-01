import { act, useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { ResponsiveTable } from "./ResponsiveTable";

function Demo() {
  const [rows, setRows] = useState(["Alice"]);
  return (
    <>
      <button onClick={() => setRows(["Alice", "Bob"])}>add</button>
      <ResponsiveTable>
        <TableHead>
          <TableRow>
            <TableCell>Client</TableCell>
            <TableCell align="right">Amount (MWK)</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r}>
              <TableCell>{r}</TableCell>
              <TableCell align="right">100.00</TableCell>
              <TableCell align="right">
                <button>Open</button>
              </TableCell>
            </TableRow>
          ))}
          <TableRow>
            <TableCell colSpan={3}>Nothing more.</TableCell>
          </TableRow>
        </TableBody>
      </ResponsiveTable>
    </>
  );
}

describe("ResponsiveTable", () => {
  afterEach(cleanup);

  it("labels each cell from its column header", () => {
    render(<Demo />);
    expect(screen.getByText("Alice").getAttribute("data-label")).toBe("Client");
    expect(screen.getAllByText("100.00")[0].getAttribute("data-label")).toBe("Amount (MWK)");
    expect(screen.getByText("Open").closest("td")?.getAttribute("data-label")).toBe("Actions");
  });

  it("leaves full-width rows unlabelled", () => {
    render(<Demo />);
    expect(screen.getByText("Nothing more.").getAttribute("data-label")).toBe("");
  });

  it("labels rows added later (paging, refresh)", async () => {
    render(<Demo />);
    await act(async () => {
      screen.getByText("add").click();
    });
    // the MutationObserver runs as a microtask after React commits
    await act(async () => {});
    expect(screen.getByText("Bob").getAttribute("data-label")).toBe("Client");
  });
});
