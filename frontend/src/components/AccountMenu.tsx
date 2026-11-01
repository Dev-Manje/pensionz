import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import ListItemIcon from "@mui/material/ListItemIcon";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Typography from "@mui/material/Typography";
import AccountCircleOutlinedIcon from "@mui/icons-material/AccountCircleOutlined";
import KeyOutlinedIcon from "@mui/icons-material/KeyOutlined";

// The signed-in user's own settings, for every role. On a phone only the
// icon shows; the email is inside the menu.
export function AccountMenu({ email }: { email: string }) {
  const navigate = useNavigate();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  function go(path: string) {
    setAnchor(null);
    navigate(path);
  }

  return (
    <>
      <Button
        color="inherit"
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-label="Your account"
        aria-haspopup="menu"
        startIcon={<AccountCircleOutlinedIcon />}
        sx={{
          textTransform: "none",
          color: "text.secondary",
          minWidth: 40,
          px: { xs: 1, sm: 1.5 },
          "& .MuiButton-startIcon": { mr: { xs: 0, sm: 1 } },
        }}
      >
        <Typography variant="body2" component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
          {email}
        </Typography>
      </Button>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 2, py: 1 }}>
          Signed in as <b>{email}</b>
        </Typography>
        <Divider />
        <MenuItem onClick={() => go("/account/password")}>
          <ListItemIcon>
            <KeyOutlinedIcon fontSize="small" />
          </ListItemIcon>
          Change password
        </MenuItem>
      </Menu>
    </>
  );
}
