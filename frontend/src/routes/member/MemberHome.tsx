import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { BRAND } from "../../brand";

// Member portal landing page (FR-PRT-002). Balances by component, statements,
// beneficiaries and claims arrive in Phase 7 once memberships exist.
export function MemberHome() {
  const { user } = useAuth();
  const firstName = user?.full_name.split(" ")[0] || "there";
  return (
    <Stack spacing={2} sx={{ maxWidth: 640 }}>
      <Typography variant="h1">Hello, {firstName}</Typography>
      <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
        <Stack spacing={1}>
          <Typography variant="h2">Your pension</Typography>
          <Typography color="text.secondary">
            We are linking your sign-in to your membership record. Once that is done you will see your savings,
            statements and beneficiaries here. If this takes longer than a few days, contact {BRAND.administrator}.
          </Typography>
        </Stack>
      </Paper>
    </Stack>
  );
}
