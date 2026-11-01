import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
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
import { DetailField, DetailSection } from "../../../../components/DetailSection";
import { LoadingState } from "../../../../components/LoadingState";
import { PageHeader } from "../../../../components/PageHeader";
import { ResponsiveTable } from "../../../../components/ResponsiveTable";
import { StatusChip } from "../../../../components/StatusChip";
import { useCategory } from "../../../../queries/categories";
import { useScheme } from "../../../../queries/schemes";
import { formatDate } from "../../../../utils/date";
import { SALARY_BASIS_LABELS, type CategoryTerms } from "../../../../api/types";
import { rateLabel, vestedLabel } from "./categoryLabels";

function Terms({ t, title }: { t: CategoryTerms; title: string }) {
  const db = t.design === "db";
  return (
    <Stack spacing={2}>
      <DetailSection title={title}>
        <DetailField label="Employee contribution">{rateLabel(t.employee_rate_type, t.employee_rate)}</DetailField>
        <DetailField label="Employer contribution">{rateLabel(t.employer_rate_type, t.employer_rate)}</DetailField>
        <DetailField label="Pensionable salary">{SALARY_BASIS_LABELS[t.salary_basis]}</DetailField>
        <DetailField label="Normal retirement age">{t.normal_retirement_age}</DetailField>
        <DetailField label="Entry ages">
          {t.min_entry_age ?? "any"} to {t.max_entry_age ?? "any"}
        </DetailField>
        <DetailField label="Waiting period">{t.waiting_period_months ? `${t.waiting_period_months} months` : "None"}</DetailField>
        {db ? (
          <>
            <DetailField label="Accrual">1/{t.accrual_denominator} of final salary per year of service</DetailField>
            <DetailField label="Final salary">Average of the last {t.final_salary_months} months</DetailField>
          </>
        ) : (
          <>
            <DetailField label="Default investment option">{t.default_investment_option}</DetailField>
            <DetailField label="Member investment choice">{t.member_choice_allowed ? "Allowed" : "Not allowed"}</DetailField>
            <DetailField label="Voluntary contributions (AVC)">{t.avc_allowed ? "Allowed" : "Not allowed"}</DetailField>
          </>
        )}
        <DetailField label="Group life cover">{t.group_life_multiple ? `${Number(t.group_life_multiple)} × annual salary` : "None"}</DetailField>
        {!db && (
          <DetailField label="Vesting of employer money">
            {t.vesting_scale.length === 0
              ? "Fully vested from joining"
              : t.vesting_scale.map((s) => (
                  <span key={s.years} style={{ display: "block" }}>
                    {s.years} years: {vestedLabel(s.vested_pct)}
                  </span>
                ))}
          </DetailField>
        )}
      </DetailSection>
    </Stack>
  );
}

export function CategoryDetailPage() {
  const { fundId, schemeId, categoryId } = useParams();
  const query = useCategory(categoryId);
  const scheme = useScheme(schemeId);

  if (query.isLoading || scheme.isLoading) return <LoadingState />;
  if (query.error || !query.data || !scheme.data) {
    return <Alert severity="error">{query.error?.message ?? scheme.error?.message ?? "Category not found"}</Alert>;
  }
  const c = query.data;
  const s = scheme.data;
  const base = `/funds/${fundId}/employers/${schemeId}`;

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        <Link component={RouterLink} to={`/funds/${fundId}?tab=employers`} underline="hover" color="inherit">
          {s.fund_code}
        </Link>
        <Link component={RouterLink} to={`${base}?tab=categories`} underline="hover" color="inherit">
          {s.code}
        </Link>
        <Typography color="text.primary">{c.code}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={c.name}
        description={`${c.code} · benefit category of ${s.name} · ${c.design === "db" ? "defined benefit" : "defined contribution"}`}
        action={
          s.can_edit &&
          !c.pending_approval_id && (
            <Button variant="contained" component={RouterLink} to={`${base}/categories/${c.id}/edit`}>
              Change category
            </Button>
          )
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, mt: -1.5 }}>
        <StatusChip status={c.status} />
      </Stack>
      {c.pending_approval_id && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" component={RouterLink} to={`/approvals/${c.pending_approval_id}`}>
              View change
            </Button>
          }
        >
          A change to this category is waiting for approval.
        </Alert>
      )}
      <Stack spacing={2}>
        {c.current ? (
          <Terms t={c.current} title={`Terms in force since ${formatDate(c.current.effective_from)}`} />
        ) : (
          <Alert severity="info">This category's first terms start on {formatDate(c.upcoming?.effective_from)}.</Alert>
        )}
        {c.upcoming && <Terms t={c.upcoming} title={`Scheduled from ${formatDate(c.upcoming.effective_from)}`} />}
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            History of terms
          </Typography>
          <TableContainer>
            <ResponsiveTable size="small">
              <TableHead>
                <TableRow>
                  <TableCell>From</TableCell>
                  <TableCell align="right">Employee</TableCell>
                  <TableCell align="right">Employer</TableCell>
                  <TableCell align="right">Retirement age</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {c.history.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(t.effective_from)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{rateLabel(t.employee_rate_type, t.employee_rate)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{rateLabel(t.employer_rate_type, t.employer_rate)}</TableCell>
                    <TableCell align="right">{t.normal_retirement_age}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </TableContainer>
        </Paper>
      </Stack>
    </>
  );
}
