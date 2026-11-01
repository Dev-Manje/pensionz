import { useState } from "react";
import {
  Link as RouterLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlTab } from "../../../hooks/useUrlState";
import { createKyc } from "../../../api/kyc";
import { useKyc, useKycAction, useKycList } from "../../../queries/kyc";
import { formatDateTime } from "../../../utils/date";
import {
  CLIENT_TYPE_LABELS,
  type ClientType,
  type KycStatus,
  type KycSummary,
} from "../../../api/types";
import { KycExpiring } from "./KycExpiring";
import { KycForm } from "./KycForm";
import { KycReview } from "./KycReview";

const VIEWS = ["queue", "drafts", "senior", "expiring", "all"] as const;
type View = (typeof VIEWS)[number];
const VIEW_STATUS: Record<View, KycStatus | null> = {
  queue: null,
  drafts: null,
  senior: "awaiting_senior_approval",
  expiring: null,
  all: null,
};
const CAPTURE_ROLES = ["compliance", "relationship_manager", "member_admin"];

const shortType: Record<ClientType, string> = {
  corporate: "Corporate",
  group: "Group",
  individual: "Individual",
};

function NewApplicationDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const [type, setType] = useState<ClientType>("corporate");
  const create = useKycAction((t: ClientType) => createKyc(t));

  async function go() {
    try {
      const app = await create.mutateAsync(type);
      navigate(`/kyc/${app.id}`);
    } catch (e) {
      feedback.error(
        e instanceof Error ? e.message : "Couldn't start the application.",
      );
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Capture a KYC application</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" sx={{ mb: 1 }}>
          Who is the client? Individuals use the individual form.
        </Typography>
        <RadioGroup
          value={type}
          onChange={(e) => setType(e.target.value as ClientType)}
        >
          {(Object.keys(CLIENT_TYPE_LABELS) as ClientType[]).map((t) => (
            <FormControlLabel
              key={t}
              value={t}
              control={<Radio />}
              label={CLIENT_TYPE_LABELS[t]}
            />
          ))}
        </RadioGroup>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={create.isPending}>
          {create.isPending ? "Starting…" : "Start"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function KycList() {
  const { user } = useAuth();
  const canCapture = CAPTURE_ROLES.some((r) =>
    user?.roles.includes(r as never),
  );
  const [view, setView] = useUrlTab(VIEWS);
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const query = useKycList(VIEW_STATUS[view], q.trim());
  const rows = (query.data ?? []).filter((a: KycSummary) =>
    view === "queue"
      ? ["submitted", "in_review"].includes(a.status)
      : view === "drafts"
        ? ["draft", "returned"].includes(a.status)
        : true,
  );

  return (
    <>
      <PageHeader
        title="KYC"
        description="Client onboarding applications — corporate, group and individual. Compliance reviews every document; high-risk clients also need an administrator's approval."
        action={
          canCapture && (
            <Button variant="contained" onClick={() => setCreating(true)}>
              Capture application
            </Button>
          )
        }
      />
      <Tabs value={view} onChange={(_, v: View) => setView(v)} sx={{ mb: 2 }}>
        <Tab value="queue" label="To review" />
        <Tab value="drafts" label="Drafts & returned" />
        <Tab value="senior" label="Senior approval" />
        <Tab value="expiring" label="Expiring" />
        <Tab value="all" label="All" />
      </Tabs>
      {view === "expiring" ? (
        <KycExpiring />
      ) : (
        <>
          <TextField
            label="Search by name or reference"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            size="small"
            sx={{ mb: 2, width: { xs: "100%", sm: 320 } }}
          />
          <TableContainer component={Paper}>
            <ResponsiveTable size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Reference</TableCell>
                  <TableCell>Client</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Risk</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Reviewer</TableCell>
                  <TableCell>Updated</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableStateRow
                  colSpan={7}
                  loading={query.isLoading}
                  error={query.error?.message ?? null}
                  onRetry={() => query.refetch()}
                  empty="No applications here."
                  count={rows.length}
                />
                {rows.map((a) => (
                  <TableRow key={a.id} hover>
                    <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                      <Link
                        component={RouterLink}
                        to={`/kyc/${a.id}`}
                        underline="hover"
                      >
                        {a.reference}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {a.display_name || (
                        <Typography component="span" color="text.secondary">
                          Not named yet
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{shortType[a.client_type]}</TableCell>
                    <TableCell>
                      {a.risk_rating ? (
                        <StatusChip status={a.risk_rating} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <StatusChip status={a.status} />
                    </TableCell>
                    <TableCell>{a.reviewer ?? "—"}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      {formatDateTime(a.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </TableContainer>
        </>
      )}
      {creating && <NewApplicationDialog onClose={() => setCreating(false)} />}
    </>
  );
}

function KycApplicationPage() {
  const { applicationId } = useParams();
  const query = useKyc(applicationId);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data)
    return (
      <Alert severity="error">
        {query.error?.message ?? "Application not found"}
      </Alert>
    );
  const app = query.data;
  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link
          component={RouterLink}
          to="/kyc"
          underline="hover"
          color="inherit"
        >
          KYC
        </Link>
        <Typography color="text.primary">{app.reference}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={
          app.display_name ||
          `New ${shortType[app.client_type].toLowerCase()} application`
        }
        description={`${app.reference} · ${CLIENT_TYPE_LABELS[app.client_type]}`}
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, mt: -1.5 }}>
        <StatusChip status={app.status} />
        {app.risk_rating && <StatusChip status={app.risk_rating} />}
      </Stack>
      {app.can_edit ? (
        <KycForm key={app.id} app={app} onSubmitted={() => query.refetch()} />
      ) : (
        <KycReview app={app} />
      )}
    </>
  );
}

// Staff KYC: queue + capture (/kyc) and one application (/kyc/<id>).
export function KycPage() {
  return (
    <Routes>
      <Route index element={<KycList />} />
      <Route path=":applicationId" element={<KycApplicationPage />} />
    </Routes>
  );
}
