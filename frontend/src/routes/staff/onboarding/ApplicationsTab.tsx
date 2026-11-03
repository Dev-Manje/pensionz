import { useNavigate } from "react-router-dom";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useApplications } from "../../../queries/employerApplications";
import type { EmployerApplicationStatus } from "../../../api/employerApplications";
import { formatDate } from "../../../utils/date";
import { APPLICATION_STAFF_TEXT } from "./onboardingLabels";

// Employers applying to join a fund, sent in by their principal officers.
export function ApplicationsTab() {
  const [filter, setFilter] = useUrlParam("status");
  const status = (filter || undefined) as EmployerApplicationStatus | undefined;
  const apps = useApplications(status);
  const navigate = useNavigate();
  const rows = apps.data ?? [];
  return (
    <>
      <TextField select size="small" label="Status" value={filter ?? ""} onChange={(e) => setFilter(e.target.value || null)} sx={{ mb: 2, minWidth: 240 }}>
        <MenuItem value="">All</MenuItem>
        {(Object.keys(APPLICATION_STAFF_TEXT) as EmployerApplicationStatus[])
          .filter((s) => s !== "draft")
          .map((s) => (
            <MenuItem key={s} value={s}>{APPLICATION_STAFF_TEXT[s].label}</MenuItem>
          ))}
      </TextField>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Employer</TableCell>
              <TableCell>Fund</TableCell>
              <TableCell>Officer</TableCell>
              <TableCell>KYC</TableCell>
              <TableCell>Sent</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={6}
              loading={apps.isLoading}
              error={apps.error?.message ?? null}
              onRetry={() => apps.refetch()}
              empty={status ? "No applications with that status." : "No employer applications yet. Officers apply from the portal."}
              count={rows.length}
            />
            {rows.map((a) => {
              const st = APPLICATION_STAFF_TEXT[a.status];
              return (
                <TableRow key={a.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/onboarding/applications/${a.id}`)}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>{a.details.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{a.reference}</Typography>
                  </TableCell>
                  <TableCell>{a.fund_code}</TableCell>
                  <TableCell>{a.officer_name}</TableCell>
                  <TableCell>{a.kyc_status ? <StatusChip status={a.kyc_status} /> : "—"}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(a.submitted_at)}</TableCell>
                  <TableCell>
                    <StatusChip status={a.status} label={st.label} tone={st.tone} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </>
  );
}
