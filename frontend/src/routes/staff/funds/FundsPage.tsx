import { useState } from "react";
import { Link as RouterLink, Route, Routes, useNavigate } from "react-router-dom";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useAuth } from "../../../auth/AuthContext";
import { useFunds } from "../../../queries/funds";
import { FUND_TYPE_LABELS } from "../../../api/types";
import { FundDetailPage } from "./FundDetailPage";
import { FundFormPage } from "./FundFormPage";

// Setup → Funds (FR-CFG-001): /funds, /funds/new, /funds/<id>, /funds/<id>/edit.
export function FundsPage() {
  return (
    <Routes>
      <Route index element={<FundList />} />
      <Route path="new" element={<FundFormPage />} />
      <Route path=":fundId" element={<FundDetailPage />} />
      <Route path=":fundId/edit" element={<FundFormPage />} />
    </Routes>
  );
}

function FundList() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canCreate = user?.roles.includes("scheme_config_maker") ?? false;
  const [q, setQ] = useState("");
  const funds = useFunds(q.trim());
  const rows = funds.data ?? [];

  return (
    <>
      <PageHeader
        title="Funds"
        description="The pension funds you administer: registration, contact details, trustees and bank accounts. New funds and changes are approved by a scheme-setup checker."
        action={canCreate && <Button variant="contained" onClick={() => navigate("/funds/new")}>Add fund</Button>}
      />
      <TextField
        label="Search by code or name"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        size="small"
        sx={{ mb: 2, width: { xs: "100%", sm: 320 } }}
      />
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Fund</TableCell>
              <TableCell>Type</TableCell>
              <TableCell align="right">Trustees</TableCell>
              <TableCell align="right">Bank accounts</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={6}
              loading={funds.isLoading}
              error={funds.error?.message ?? null}
              onRetry={() => funds.refetch()}
              empty={
                q
                  ? "No funds match that search."
                  : canCreate
                    ? "No funds yet. Add the first one with “Add fund”."
                    : "You don't administer any funds yet. Ask an administrator to give you access."
              }
              count={rows.length}
            />
            {rows.map((f) => (
              <TableRow key={f.id} hover>
                <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                  <Link component={RouterLink} to={`/funds/${f.id}`} underline="hover">
                    {f.code}
                  </Link>
                </TableCell>
                <TableCell>{f.name}</TableCell>
                <TableCell>{FUND_TYPE_LABELS[f.fund_type]}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{f.trustee_count}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{f.bank_account_count}</TableCell>
                <TableCell>
                  <StatusChip status={f.status} />
                  {f.pending_approval_id && <StatusChip status="change_pending" sx={{ ml: 0.5 }} />}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </>
  );
}
