import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";

// Building blocks for long setup forms (fund, employer, category…): titled
// sections, a responsive field grid, and repeatable rows.

export function FormSection({ title, description, children, action }: { title: string; description?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <Paper component="section" sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 2, gap: 2 }}>
        <Box>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            {title}
          </Typography>
          {description && (
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          )}
        </Box>
        {action && <Box sx={{ flexShrink: 0, "& .MuiButton-root": { whiteSpace: "nowrap" } }}>{action}</Box>}
      </Stack>
      {children}
    </Paper>
  );
}

export function FormGrid({ children }: { children: ReactNode }) {
  return <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(3, 1fr)" }, gap: 2 }}>{children}</Box>;
}

// A row in a repeatable list (trustee, bank account…), with its remove button.
export function RepeatRow({ label, onRemove, children }: { label: string; onRemove: () => void; children: ReactNode }) {
  return (
    <Box sx={{ border: 1, borderColor: "divider", borderRadius: 1, p: 2 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        <IconButton onClick={onRemove} aria-label={`Remove ${label}`} title="Remove" size="small">
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Stack>
      <FormGrid>{children}</FormGrid>
    </Box>
  );
}
