import type { FormEvent, ReactNode } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { BRAND } from "../brand";

// The centred card used by the signed-out pages (sign in, forgot / reset password).
export function AuthLayout({ children, onSubmit }: { children: ReactNode; onSubmit?: (e: FormEvent) => void }) {
  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 2,
        background: `linear-gradient(180deg, ${BRAND.colors.authGradientTop} 0%, ${BRAND.colors.background} 100%)`,
      }}
    >
      <Paper component={onSubmit ? "form" : "div"} onSubmit={onSubmit} sx={{ p: { xs: 3, sm: 4 }, maxWidth: 420, width: "100%" }}>
        <Stack spacing={2.5}>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main" }}>
            {BRAND.name}
          </Typography>
          {children}
        </Stack>
      </Paper>
    </Box>
  );
}
