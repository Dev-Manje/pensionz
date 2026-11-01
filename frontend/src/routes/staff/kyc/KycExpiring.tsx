import { Link as RouterLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { apiFetch } from "../../../api/client";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { formatDate } from "../../../utils/date";

interface ExpiringItem {
  kind: "review" | "document";
  party_id: string;
  party_name: string;
  label: string;
  due: string;
  days_left: number;
  application_id: string | null;
}

function when(days: number): string {
  if (days > 0) return `in ${days} day${days === 1 ? "" : "s"}`;
  if (days === 0) return "today";
  return `${-days} day${days === -1 ? "" : "s"} overdue`;
}

// KYC reviews and identity documents due in the next 60 days, or overdue (FR-ONB-104).
export function KycExpiring() {
  const query = useQuery({ queryKey: ["kyc", "expiring"], queryFn: () => apiFetch<ExpiringItem[]>("/kyc/expiring?within_days=60") });
  const rows = query.data ?? [];
  return (
    <>
      <Typography color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Clients whose periodic KYC review is due, and approved identity documents or permits about to expire. Compliance is reminded 30
        and 7 days before, on the day, and weekly once overdue.
      </Typography>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Client</TableCell>
              <TableCell>What</TableCell>
              <TableCell>Due</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={4} loading={query.isLoading} error={query.error?.message ?? null} onRetry={() => query.refetch()} empty="Nothing due in the next 60 days." count={rows.length} />
            {rows.map((r) => (
              <TableRow key={`${r.kind}-${r.party_id}-${r.label}`} hover>
                <TableCell sx={{ fontWeight: 600 }}>
                  {r.application_id ? (
                    <Link component={RouterLink} to={`/kyc/${r.application_id}`} underline="hover">
                      {r.party_name}
                    </Link>
                  ) : (
                    r.party_name
                  )}
                </TableCell>
                <TableCell>{r.label}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {formatDate(r.due)} · {when(r.days_left)}
                </TableCell>
                <TableCell>
                  <StatusChip status={r.days_left < 0 ? "overdue" : r.days_left <= 7 ? "due_soon" : "upcoming"} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </>
  );
}
