import { useState } from "react";
import Button from "@mui/material/Button";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";

export type RowAction = { label: string; onClick: () => void; color?: "warning" | "error" };

// A table row's actions: one action is a plain button; two or more collapse
// into an "Actions" menu so the column keeps a fixed, narrow width at every
// screen size instead of overflowing the table.
export function RowActions({ actions, label = "Actions" }: { actions: RowAction[]; label?: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  if (actions.length === 0) return null;
  if (actions.length === 1) {
    const [a] = actions;
    return (
      <Button size="small" color={a.color} onClick={a.onClick}>
        {a.label}
      </Button>
    );
  }
  return (
    <>
      <Button
        size="small"
        variant="outlined"
        endIcon={<ArrowDropDownIcon />}
        aria-haspopup="menu"
        aria-expanded={!!anchor}
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        {label}
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
        {actions.map((a) => (
          <MenuItem
            key={a.label}
            sx={{ minHeight: 44, color: a.color ? `${a.color}.main` : undefined }}
            onClick={() => {
              setAnchor(null);
              a.onClick();
            }}
          >
            {a.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
