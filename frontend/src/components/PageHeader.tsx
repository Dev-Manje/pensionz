import type { ReactNode } from "react";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Stack direction="row" spacing={2} useFlexGap sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 3, flexWrap: "wrap" }}>
      <Stack spacing={0.5}>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {description && (
          <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
            {description}
          </Typography>
        )}
      </Stack>
      {action}
    </Stack>
  );
}
