import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";
import { BRAND } from "../../brand";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useKyc } from "../../queries/kyc";
import { poKeys, useMySchemes } from "../../queries/po";
import { formatDateTime } from "../../utils/date";
import { KycDocuments } from "../staff/kyc/KycDocuments";
import { KycForm } from "../staff/kyc/KycForm";
import { KycAnswers } from "../staff/kyc/KycReview";
import { KYC_STATUS_TEXT } from "./poLabels";
import { schemePath } from "./PoSchemePage";

// One of the employer's KYC applications in the portal: the same stepper staff
// use while it's a draft or returned, read-only once it's with compliance.
export function PoKycPage() {
  const { applicationId } = useParams();
  const navigate = useNavigate();
  // Started from an employer application (no employer yet): back there afterwards.
  const [search] = useSearchParams();
  const fromApplication = search.get("application");
  const queryClient = useQueryClient();
  const query = useKyc(applicationId);
  const schemes = useMySchemes();
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Application not found"}</Alert>;
  const app = query.data;
  const scheme = schemes.data?.find((s) => s.id === app.scheme_id);
  const status = KYC_STATUS_TEXT[app.status];
  const title = app.is_change ? "Change of details" : "Organisation KYC";

  function submitted() {
    queryClient.invalidateQueries({ queryKey: poKeys.all });
    queryClient.invalidateQueries({ queryKey: ["employer-applications"] });
    navigate(fromApplication ? `/po/applications/${fromApplication}` : scheme ? schemePath(scheme.id, "organisation") : "/po");
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">
          My schemes
        </Link>
        {fromApplication && !scheme && (
          <Link component={RouterLink} to={`/po/applications/${fromApplication}`} underline="hover" color="inherit">
            Employer application
          </Link>
        )}
        {scheme && (
          <Link component={RouterLink} to={schemePath(scheme.id, "organisation")} underline="hover" color="inherit">
            {scheme.name}
          </Link>
        )}
        <Typography color="text.primary">{app.reference}</Typography>
      </Breadcrumbs>
      <div>
        <Typography variant="h1">{app.display_name || title}</Typography>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5 }}>
          <Typography color="text.secondary">
            {title} · {app.reference}
          </Typography>
          <StatusChip status={app.status} label={status.label} tone={status.tone} />
        </Stack>
      </div>
      {app.can_edit ? (
        <KycForm key={app.id} app={app} onSubmitted={submitted} />
      ) : (
        <>
          {["submitted", "in_review", "awaiting_senior_approval"].includes(app.status) && (
            <Alert severity="info">
              Sent {app.submitted_at ? formatDateTime(app.submitted_at) : ""}. It's with {BRAND.administrator}, who checks the details and
              documents — you'll be told by email when it's decided, or if anything needs changing.
            </Alert>
          )}
          {app.status === "approved" && <Alert severity="success">Approved {app.decided_at ? formatDateTime(app.decided_at) : ""}.</Alert>}
          {app.status === "rejected" && <Alert severity="error">Not approved: {app.decision_reason}</Alert>}
          <KycDocuments app={app} mode="view" />
          <KycAnswers app={app} />
        </>
      )}
    </Stack>
  );
}
