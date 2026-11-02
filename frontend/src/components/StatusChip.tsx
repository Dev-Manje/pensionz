import Chip, { type ChipProps } from "@mui/material/Chip";
import { statusLabel, statusTone, type StatusTone } from "../utils/labels";

// A status code as a readable, consistently coloured chip. Pass `tone` only
// when a screen means something different by the colour, and `label` when
// the screen has its own words for it.
export function StatusChip({ status, tone, label, ...rest }: { status: string; tone?: StatusTone; label?: string } & Omit<ChipProps, "label" | "color">) {
  return <Chip size="small" label={label ?? statusLabel(status)} color={tone ?? statusTone(status)} {...rest} />;
}
