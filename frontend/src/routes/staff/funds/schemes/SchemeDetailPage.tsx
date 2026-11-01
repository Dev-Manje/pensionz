import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { DetailField, DetailSection } from "../../../../components/DetailSection";
import { LoadingState } from "../../../../components/LoadingState";
import { PageHeader } from "../../../../components/PageHeader";
import { ResponsiveTable } from "../../../../components/ResponsiveTable";
import { StatusChip } from "../../../../components/StatusChip";
import { TableStateRow } from "../../../../components/TableStateRow";
import { useUrlTab } from "../../../../hooks/useUrlState";
import { useScheme } from "../../../../queries/schemes";
import { formatDate } from "../../../../utils/date";
import { BILLING_FREQUENCY_LABELS, type Scheme } from "../../../../api/types";
import { dueDayLabel } from "./schemeLabels";
import { SchemeCategoriesTab } from "../categories/SchemeCategoriesTab";

const TABS = ["details", "categories", "officers"] as const;
type SchemeTab = (typeof TABS)[number];

function Details({ scheme }: { scheme: Scheme }) {
  const address = [scheme.address_line1, scheme.address_line2, scheme.address_line3].filter(Boolean);
  return (
    <Stack spacing={2}>
      <DetailSection title="Employer">
        <DetailField label="Employer code">{scheme.code}</DetailField>
        <DetailField label="Registration number">{scheme.registration_number}</DetailField>
        <DetailField label="TPIN">{scheme.tpin}</DetailField>
        <DetailField label="Joined the fund">{scheme.join_date && formatDate(scheme.join_date)}</DetailField>
        {scheme.exit_date && <DetailField label="Left the fund">{formatDate(scheme.exit_date)}</DetailField>}
      </DetailSection>
      <DetailSection title="Contributions">
        <DetailField label="Due by">{dueDayLabel(scheme.contribution_day)}</DetailField>
        <DetailField label="Billing">{BILLING_FREQUENCY_LABELS[scheme.billing_frequency]}</DetailField>
      </DetailSection>
      <DetailSection title="Address and contact">
        <DetailField label="Address">
          {address.length > 0 &&
            address.map((line) => (
              <span key={line} style={{ display: "block" }}>
                {line}
              </span>
            ))}
        </DetailField>
        <DetailField label="Phone">{scheme.phone}</DetailField>
        <DetailField label="Email">{scheme.email}</DetailField>
        <DetailField label="Contact person">{scheme.contact_name}</DetailField>
        <DetailField label="Contact email">{scheme.contact_email}</DetailField>
        <DetailField label="Contact phone">{scheme.contact_phone}</DetailField>
      </DetailSection>
    </Stack>
  );
}

function Officers({ scheme }: { scheme: Scheme }) {
  return (
    <Stack spacing={2}>
      <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
        Principal officers remit this employer's contributions and manage its members in the portal. Linking or removing one is
        approved like any other change to the employer.
      </Typography>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={2} loading={false} error={null} empty="No principal officers linked yet. Link them with “Edit employer”." count={scheme.officers.length} />
            {scheme.officers.map((o) => (
              <TableRow key={o.user_id}>
                <TableCell sx={{ fontWeight: 500 }}>{o.full_name}</TableCell>
                <TableCell>{o.email}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Stack>
  );
}

export function SchemeDetailPage() {
  const { fundId, schemeId } = useParams();
  const query = useScheme(schemeId);
  const [tab, setTab] = useUrlTab(TABS);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button component={RouterLink} to={`/funds/${fundId}?tab=employers`}>Back to fund</Button>}>
        {query.error?.message ?? "Employer not found"}
      </Alert>
    );
  }
  const scheme = query.data;

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        <Link component={RouterLink} to={`/funds/${scheme.fund_id}?tab=employers`} underline="hover" color="inherit">
          {scheme.fund_code}
        </Link>
        <Typography color="text.primary">{scheme.code}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={scheme.name}
        description={`${scheme.code} · employer in ${scheme.fund_name}`}
        action={
          scheme.can_edit &&
          !scheme.pending_approval_id && (
            <Button variant="contained" component={RouterLink} to={`/funds/${scheme.fund_id}/employers/${scheme.id}/edit`}>
              Edit employer
            </Button>
          )
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, mt: -1.5 }}>
        <StatusChip status={scheme.status} />
      </Stack>
      {scheme.pending_approval_id && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" component={RouterLink} to={`/approvals/${scheme.pending_approval_id}`}>
              View change
            </Button>
          }
        >
          A change to this employer is waiting for approval. It can be edited again once that change is decided.
        </Alert>
      )}
      <Tabs value={tab} onChange={(_, v: SchemeTab) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" scrollButtons="auto">
        <Tab value="details" label="Details" />
        <Tab value="categories" label="Benefit categories" />
        <Tab value="officers" label={`Principal officers (${scheme.officers.length})`} />
      </Tabs>
      {tab === "details" && <Details scheme={scheme} />}
      {tab === "categories" && <SchemeCategoriesTab scheme={scheme} />}
      {tab === "officers" && <Officers scheme={scheme} />}
    </>
  );
}
