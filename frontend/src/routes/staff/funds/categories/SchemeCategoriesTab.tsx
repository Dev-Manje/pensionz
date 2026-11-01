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
import { useCategories } from "../../../../queries/categories";
import type { Scheme } from "../../../../api/types";
import { rateLabel } from "./categoryLabels";

// An employer's benefit categories (FR-CFG-004) with the terms in force today.
export function SchemeCategoriesTab({ scheme }: { scheme: Scheme }) {
  const query = useCategories(scheme.id);
  const rows = query.data ?? [];
  const canAdd = scheme.can_edit && scheme.status === "active";
  const base = `/funds/${scheme.fund_id}/employers/${scheme.id}/categories`;

  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
          Groups of this employer's staff with their own contribution rates, retirement age, vesting and cover. Rate changes take
          effect from a date; earlier months keep the old rates.
        </Typography>
        {canAdd && (
          <Button variant="contained" component={RouterLink} to={`${base}/new`}>
            Add category
          </Button>
        )}
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Category</TableCell>
              <TableCell align="right">Employee</TableCell>
              <TableCell align="right">Employer</TableCell>
              <TableCell align="right">Retirement age</TableCell>
              <TableCell>Default option</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={7}
              loading={query.isLoading}
              error={query.error?.message ?? null}
              onRetry={() => query.refetch()}
              empty={canAdd ? "No categories yet. Add the first with “Add category”." : "No categories for this employer yet."}
              count={rows.length}
            />
            {rows.map((c) => {
              const t = c.current ?? c.upcoming;
              return (
                <TableRow key={c.id} hover>
                  <TableCell sx={{ fontWeight: 600 }}>
                    <Link component={RouterLink} to={`${base}/${c.id}`} underline="hover">
                      {c.code}
                    </Link>
                  </TableCell>
                  <TableCell>{c.name}</TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                    {t ? rateLabel(t.employee_rate_type, t.employee_rate) : "—"}
                  </TableCell>
                  <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                    {t ? rateLabel(t.employer_rate_type, t.employer_rate) : "—"}
                  </TableCell>
                  <TableCell align="right">{t?.normal_retirement_age ?? "—"}</TableCell>
                  <TableCell>{t?.default_investment_option ?? (c.design === "db" ? "Defined benefit" : "—")}</TableCell>
                  <TableCell>
                    <StatusChip status={c.status} />
                    {!c.current && c.upcoming && <StatusChip status="scheduled" tone="info" sx={{ ml: 0.5 }} />}
                    {c.pending_approval_id && <StatusChip status="change_pending" sx={{ ml: 0.5 }} />}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Stack>
  );
}
