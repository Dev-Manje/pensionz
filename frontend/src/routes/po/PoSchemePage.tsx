import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../components/LoadingState";
import { useUrlTab } from "../../hooks/useUrlState";
import { useMySchemes } from "../../queries/po";
import { PoOrganisation } from "./PoOrganisation";

export const SCHEME_TABS = ["organisation"] as const;
export type SchemeTab = (typeof SCHEME_TABS)[number];

const TAB_LABELS: Record<SchemeTab, string> = {
  organisation: "Organisation & KYC",
};

// Link to one section of an employer's page.
export function schemePath(schemeId: string, tab: SchemeTab = SCHEME_TABS[0]) {
  return tab === SCHEME_TABS[0] ? `/po/schemes/${schemeId}` : `/po/schemes/${schemeId}?tab=${tab}`;
}

// One employer the officer acts for, its sections as tabs. Officers of several
// employers switch here without going back to the dashboard.
export function PoSchemePage() {
  const { schemeId = "" } = useParams();
  const navigate = useNavigate();
  const schemes = useMySchemes();
  const [tab, setTab] = useUrlTab(SCHEME_TABS);
  if (schemes.isLoading) return <LoadingState />;
  if (schemes.error) return <Alert severity="error">{schemes.error.message}</Alert>;
  const all = schemes.data ?? [];
  const scheme = all.find((s) => s.id === schemeId);
  if (!scheme) return <Alert severity="error">This employer isn't linked to your sign-in.</Alert>;

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">
          My schemes
        </Link>
        <Typography color="text.primary">{scheme.name}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
        <div>
          <Typography variant="h1">{scheme.name}</Typography>
          <Typography color="text.secondary">
            Employer code {scheme.code} · {scheme.fund_name}
          </Typography>
        </div>
        {all.length > 1 && (
          <TextField
            select
            size="small"
            label="Employer"
            value={scheme.id}
            onChange={(e) => navigate(schemePath(e.target.value, tab))}
            sx={{ minWidth: { sm: 260 } }}
          >
            {all.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.name} — {s.fund_code}
              </MenuItem>
            ))}
          </TextField>
        )}
      </Stack>
      <Tabs value={tab} onChange={(_, v: SchemeTab) => setTab(v)} variant="scrollable" allowScrollButtonsMobile>
        {SCHEME_TABS.map((t) => (
          <Tab key={t} value={t} label={TAB_LABELS[t]} />
        ))}
      </Tabs>
      {tab === "organisation" && <PoOrganisation schemeId={scheme.id} />}
    </Stack>
  );
}
