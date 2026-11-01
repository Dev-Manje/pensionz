import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { BRAND } from "../../brand";

// Principal officer portal landing page (FR-PRT-001). Remittances, schedules,
// members and arrears arrive in Phase 5 once schemes exist.
export function PoHome() {
  const { user } = useAuth();
  const firstName = user?.full_name.split(" ")[0] || "there";
  return (
    <Stack spacing={2} sx={{ maxWidth: 760 }}>
      <Typography variant="h1">Hello, {firstName}</Typography>
      <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
        <Stack spacing={1}>
          <Typography variant="h2">Your schemes</Typography>
          <Typography color="text.secondary">
            Your sign-in has not been linked to a scheme yet. Once {BRAND.administrator} links it, you will be able to
            send monthly contribution schedules, add and update members, and follow each remittance here.
          </Typography>
        </Stack>
      </Paper>
    </Stack>
  );
}
