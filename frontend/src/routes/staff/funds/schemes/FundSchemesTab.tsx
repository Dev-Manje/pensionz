import { Link as RouterLink } from "react-router-dom";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { ResponsiveTable } from "../../../../components/ResponsiveTable";
import { StatusChip } from "../../../../components/StatusChip";
import { TableStateRow } from "../../../../components/TableStateRow";
import { useSchemes } from "../../../../queries/schemes";
import { BILLING_FREQUENCY_LABELS, type Fund } from "../../../../api/types";
import { dueDayLabel } from "./schemeLabels";

// The fund's participating employers (FR-CFG-003).
export function FundSchemesTab({ fund }: { fund: Fund }) {
  const query = useSchemes(fund.id);
  const rows = query.data ?? [];
  const canAdd = fund.can_edit && fund.status === "active";

  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
          Employers whose staff belong to this fund, when their contributions are due, and the principal officers who remit them.
        </Typography>
        {canAdd && (
          <Button variant="contained" component={RouterLink} to={`/funds/${fund.id}/employers/new`}>
            Add employer
          </Button>
        )}
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Employer</TableCell>
              <TableCell>Contributions due</TableCell>
              <TableCell>Billing</TableCell>
              <TableCell align="right">Principal officers</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={6}
              loading={query.isLoading}
              error={query.error?.message ?? null}
              onRetry={() => query.refetch()}
              empty={canAdd ? "No employers yet. Add the first one with “Add employer”." : "No employers in this fund yet."}
              count={rows.length}
            />
            {rows.map((s) => (
              <TableRow key={s.id} hover>
                <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                  <Link component={RouterLink} to={`/funds/${fund.id}/employers/${s.id}`} underline="hover">
                    {s.code}
                  </Link>
                </TableCell>
                <TableCell>{s.name}</TableCell>
                <TableCell>{dueDayLabel(s.contribution_day)}</TableCell>
                <TableCell>{BILLING_FREQUENCY_LABELS[s.billing_frequency]}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{s.officer_count}</TableCell>
                <TableCell>
                  <StatusChip status={s.status} />
                  {s.pending_approval_id && <StatusChip status="change_pending" sx={{ ml: 0.5 }} />}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Stack>
  );
}
