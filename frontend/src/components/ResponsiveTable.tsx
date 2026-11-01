import { useLayoutEffect, useRef } from "react";
import Table, { type TableProps } from "@mui/material/Table";
import type { Theme } from "@mui/material/styles";

// A drop-in for MUI's <Table>: an ordinary table on tablets and up; on a
// phone each row becomes a card of "LABEL  value" lines, so the main facts
// read top to bottom instead of scrolling sideways. Labels come from the
// header row automatically (kept in sync as rows page/refresh), so screens
// don't have to repeat them. A cell spanning several columns (empty states,
// expanded detail rows) is shown full width without a label; an "Actions"
// cell is shown without one, right-aligned.
export function ResponsiveTable({ sx, children, ...props }: TableProps) {
  const ref = useRef<HTMLTableElement>(null);

  useLayoutEffect(() => {
    const table = ref.current;
    if (!table) return;
    const label = () => {
      const headers: string[] = [];
      table.querySelectorAll(":scope > thead > tr:last-child > th").forEach((th) => {
        const cell = th as HTMLTableCellElement;
        for (let i = 0; i < cell.colSpan; i++) headers.push(cell.colSpan > 1 ? "" : (cell.textContent ?? "").trim());
      });
      table.querySelectorAll(":scope > tbody > tr").forEach((tr) => {
        let col = 0;
        Array.from(tr.children).forEach((td) => {
          const cell = td as HTMLTableCellElement;
          const text = cell.colSpan > 1 ? "" : (headers[col] ?? "");
          if (cell.getAttribute("data-label") !== text) cell.setAttribute("data-label", text);
          col += cell.colSpan;
        });
      });
    };
    label();
    // Rows change when the page, filters or data change; attribute writes
    // above aren't childList mutations, so this can't loop.
    const observer = new MutationObserver(label);
    observer.observe(table, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return (
    <Table ref={ref} sx={[stackOnPhone, ...(Array.isArray(sx) ? sx : [sx])]} {...props}>
      {children}
    </Table>
  );
}

const stackOnPhone = (theme: Theme) => ({
  [theme.breakpoints.down("sm")]: {
    display: "block",
    minWidth: "0 !important",
    "& > thead": { display: "none" },
    "& > tbody": { display: "block" },
    "& > tbody > tr": {
      display: "block",
      py: 1,
      borderBottom: `1px solid ${theme.palette.divider}`,
      "&:last-of-type": { borderBottom: 0 },
    },
    "& > tbody > tr > td": {
      display: "block",
      position: "relative",
      border: 0,
      py: 0.5,
      pr: 2,
      pl: "calc(40% + 16px)",
      minHeight: 28,
      textAlign: "right",
      maxWidth: "none",
      whiteSpace: "normal",
      overflowWrap: "anywhere",
      "&::before": {
        content: "attr(data-label)",
        position: "absolute",
        left: 16,
        top: 4,
        width: "40%",
        textAlign: "left",
        fontSize: "0.6875rem",
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: theme.palette.text.secondary,
      },
      '&[data-label=""], &[data-label="Actions"]': { pl: 2, "&::before": { display: "none" } },
      "&:empty, &:not([data-label])": { display: "none" },
      // empty states and expanded detail rows span the table: full width, centred as written
      '&[colspan]:not([colspan="1"])': { textAlign: "center" },
      // long status chips wrap inside the card instead of being cut off
      "& .MuiChip-root": { maxWidth: "100%", height: "auto", minHeight: 24 },
      "& .MuiChip-label": { whiteSpace: "normal", py: 0.25 },
    },
  },
});
