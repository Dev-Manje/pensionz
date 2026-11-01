import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

type Values = Record<string, unknown>;

function show(value: unknown, format?: (key: string, value: unknown) => string, key = ""): string {
  if (format) return format(key, value);
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanKey(key: string) {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// Before → after for a change request, so the checker sees exactly what
// approving will change. With no `before`, it lists the proposed values.
export function DiffView({
  after,
  before,
  hide = [],
  format,
}: {
  after: Values;
  before?: Values | null;
  hide?: string[];
  format?: (key: string, value: unknown) => string;
}) {
  const keys = Object.keys(after).filter((k) => !hide.includes(k));
  if (keys.length === 0) return <Typography color="text.secondary">No details.</Typography>;
  return (
    <Table size="small" aria-label="Proposed change">
      <TableHead>
        <TableRow>
          <TableCell>Field</TableCell>
          {before && <TableCell>Now</TableCell>}
          <TableCell>{before ? "After approval" : "Value"}</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {keys.map((k) => (
          <TableRow key={k}>
            <TableCell sx={{ fontWeight: 500 }}>{humanKey(k)}</TableCell>
            {before && <TableCell sx={{ color: "text.secondary" }}>{show(before[k], format, k)}</TableCell>}
            <TableCell sx={{ fontWeight: before ? 600 : 400 }}>{show(after[k], format, k)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
