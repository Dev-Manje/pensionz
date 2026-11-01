import Chip, { type ChipProps } from "@mui/material/Chip";
import { statusLabel, statusTone, type StatusTone } from "../utils/labels";

// A status code as a readable, consistently coloured chip. Pass `tone` only
// when a screen means something different by the colour.
export function StatusChip({ status, tone, ...rest }: { status: string; tone?: StatusTone } & Omit<ChipProps, "label" | "color">) {
  return <Chip size="small" label={statusLabel(status)} color={tone ?? statusTone(status)} {...rest} />;
}
