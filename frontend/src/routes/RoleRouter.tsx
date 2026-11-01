import { useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import MenuIcon from "@mui/icons-material/Menu";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutlined";
import SavingsOutlinedIcon from "@mui/icons-material/SavingsOutlined";
import BusinessOutlinedIcon from "@mui/icons-material/BusinessOutlined";
import AccountBalanceOutlinedIcon from "@mui/icons-material/AccountBalanceOutlined";
import { useAuth } from "../auth/AuthContext";
import { RouteErrorBoundary } from "../components/RouteErrorBoundary";
import { NotificationBell } from "../components/notifications/NotificationBell";
import { AccountMenu } from "../components/AccountMenu";
import { ChangePasswordPage } from "./account/ChangePasswordPage";
import { NotificationsPage } from "./notifications/NotificationsPage";
import { StaffHome } from "./staff/StaffHome";
import { ApprovalsPage } from "./staff/approvals/ApprovalsPage";
import { UsersPage } from "./staff/admin/UsersPage";
import { FundsPage } from "./staff/funds/FundsPage";
import { MemberHome } from "./member/MemberHome";
import { PoHome } from "./po/PoHome";
import { ROLE_LABELS, STAFF_ROLES } from "../api/types";
import { BRAND } from "../brand";
import type { UserRole } from "../api/types";

const SIDEBAR_WIDTH = 224;
const SIDEBAR_WIDTH_COLLAPSED = 64;
const COLLAPSE_STORAGE_KEY = "pz_sidebar_collapsed";

interface Section {
  // URL segment: the section lives at /<path>, and anything under it belongs to it.
  path: string;
  label: string;
  icon: JSX.Element;
  roles: UserRole[];
  element: JSX.Element;
}

// Portals have their own in-page navigation; staff get the sidebar.
const PORTAL_PATHS = ["member", "po"];

// One table drives both the sidebar and the route guards, so they can't drift
// apart. A user with several roles sees the union of what each unlocks.
// Later phases add funds, employers, members, contributions, bonus, claims,
// payments, accounting and reports here (pz-frontend-architecture).
const SECTIONS: Section[] = [
  { path: "member", label: "My pension", icon: <SavingsOutlinedIcon />, roles: ["member", "individual"], element: <MemberHome /> },
  { path: "po", label: "My schemes", icon: <BusinessOutlinedIcon />, roles: ["principal_officer"], element: <PoHome /> },
  { path: "home", label: "Home", icon: <HomeOutlinedIcon />, roles: STAFF_ROLES, element: <StaffHome /> },
  { path: "approvals", label: "Approvals", icon: <CheckCircleOutlineIcon />, roles: STAFF_ROLES, element: <ApprovalsPage /> },
  { path: "funds", label: "Funds", icon: <AccountBalanceOutlinedIcon />, roles: STAFF_ROLES, element: <FundsPage /> },
  { path: "users", label: "Users", icon: <PersonOutlineIcon />, roles: ["admin", "auditor"], element: <UsersPage /> },
];

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function NavList({
  id,
  sections,
  activePath,
  collapsed,
  onNavigate,
}: {
  id: string;
  sections: Section[];
  activePath: string;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <List component="nav" id={id} aria-label="Main menu" sx={{ p: 1 }}>
      {sections.map((s) => {
        const button = (
          <ListItemButton
            key={s.path}
            component={Link}
            to={`/${s.path}`}
            onClick={onNavigate}
            selected={activePath === s.path}
            aria-current={activePath === s.path ? "page" : undefined}
            aria-label={collapsed ? s.label : undefined}
            sx={{ borderRadius: 1, mb: 0.25, minHeight: 44, justifyContent: collapsed ? "center" : "flex-start", px: collapsed ? 1.5 : 2 }}
          >
            <ListItemIcon sx={{ minWidth: 0, mr: collapsed ? 0 : 1.5, justifyContent: "center", color: "inherit" }}>{s.icon}</ListItemIcon>
            {!collapsed && <ListItemText slotProps={{ primary: { sx: { fontSize: "0.875rem", fontWeight: 500 } } }} primary={s.label} />}
          </ListItemButton>
        );
        return collapsed ? (
          <Tooltip key={s.path} title={s.label} placement="right">
            {button}
          </Tooltip>
        ) : (
          button
        );
      })}
    </List>
  );
}

function Notice({ children }: { children: string }) {
  return (
    <Paper sx={{ p: { xs: 2.5, sm: 4 }, maxWidth: 480 }}>
      <Typography>{children}</Typography>
    </Paper>
  );
}

// Phase 1 §7.2: one app, role-based routing. Every screen has its own URL
// (/clients, /clients/<id>/portfolio, /deposit-approvals ...) so refresh,
// the back button, bookmarks and shared links all work.
export function RoleRouter() {
  const { user, logout } = useAuth();
  const location = useLocation();
  // Phones and portrait tablets: the sidebar is a drawer that slides over
  // the page and closes after a choice; wider screens keep it docked.
  const narrow = useMediaQuery(useTheme().breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsedPref, setCollapsedPref] = useState(() => readCollapsed());
  if (!user) return null;
  const collapsed = collapsedPref && !narrow;

  function toggleMenu() {
    if (narrow) {
      setDrawerOpen((open) => !open);
      return;
    }
    setCollapsedPref((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // storage unavailable (private mode): the choice just isn't remembered
      }
      return next;
    });
  }

  const allowed = (s: Section) => s.roles.some((r) => user.roles.includes(r));
  const visibleSections = SECTIONS.filter(allowed);
  const hasStaffSections = visibleSections.some((s) => !PORTAL_PATHS.includes(s.path));
  // A portal-only account (member, principal officer) uses its own tabs, so no sidebar.
  const sidebarSections = hasStaffSections ? visibleSections : [];
  const activePath = location.pathname.split("/")[1] ?? "";
  const homePath = visibleSections[0] ? `/${visibleSections[0].path}` : null;
  const drawerWidth = collapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      {/* Keyboard users jump past the header and menu (WCAG 2.4.1); visible only when focused. */}
      <Box
        component="a"
        href="#main-content"
        sx={{
          position: "absolute",
          left: 8,
          top: -48,
          zIndex: (theme) => theme.zIndex.appBar + 1,
          bgcolor: "primary.main",
          color: "primary.contrastText",
          px: 2,
          py: 1,
          borderRadius: 1,
          fontWeight: 600,
          textDecoration: "none",
          "&:focus": { top: 8 },
        }}
      >
        Skip to main content
      </Box>
      <AppBar position="sticky" color="inherit" sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Toolbar sx={{ justifyContent: "space-between" }}>
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            {sidebarSections.length > 0 && (
              <IconButton
                onClick={toggleMenu}
                aria-label={narrow ? "Open menu" : collapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={narrow ? "Menu" : collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-expanded={narrow ? drawerOpen : !collapsed}
                aria-controls="app-navigation"
                sx={{ ml: -1 }}
              >
                <MenuIcon />
              </IconButton>
            )}
            {/* Links home: customers have no sidebar, so this is their way back from Notifications / Change password. */}
            <Typography
              variant="h6"
              component={Link}
              to={homePath ?? "/"}
              sx={{ fontWeight: 700, color: "primary.main", textDecoration: "none" }}
            >
              {BRAND.name}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            {/* Who's signed in is secondary on a phone (icon only); the bell and Sign out must fit. */}
            <AccountMenu email={user.email} />
            {user.roles.map((r) => (
              <Chip
                key={r}
                label={ROLE_LABELS[r] ?? r}
                size="small"
                color="primary"
                variant="outlined"
                sx={{ display: { xs: "none", md: "inline-flex" } }}
              />
            ))}
            <NotificationBell />
            <Button variant="outlined" size="small" onClick={logout}>
              Sign out
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>
      <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
        {sidebarSections.length > 0 &&
          (narrow ? (
            <Drawer
              variant="temporary"
              open={drawerOpen}
              onClose={() => setDrawerOpen(false)}
              ModalProps={{ keepMounted: true }}
              sx={{ [`& .MuiDrawer-paper`]: { width: Math.min(SIDEBAR_WIDTH + 56, 320), boxSizing: "border-box" } }}
            >
              <Toolbar>
                <Typography variant="h6" sx={{ fontWeight: 700, color: "primary.main" }}>
                  {BRAND.name}
                </Typography>
              </Toolbar>
              <NavList id="app-navigation" sections={sidebarSections} activePath={activePath} collapsed={false} onNavigate={() => setDrawerOpen(false)} />
            </Drawer>
          ) : (
            <Drawer
              variant="permanent"
              sx={{
                width: drawerWidth,
                flexShrink: 0,
                transition: (theme) => theme.transitions.create("width", { duration: theme.transitions.duration.shortest }),
                [`& .MuiDrawer-paper`]: {
                  width: drawerWidth,
                  boxSizing: "border-box",
                  position: "relative",
                  border: "none",
                  borderRight: 1,
                  borderColor: "divider",
                  overflowX: "hidden",
                  transition: (theme) => theme.transitions.create("width", { duration: theme.transitions.duration.shortest }),
                },
              }}
            >
              <NavList id="app-navigation" sections={sidebarSections} activePath={activePath} collapsed={collapsed} />
            </Drawer>
          ))}
        <Box component="main" id="main-content" tabIndex={-1} sx={{ flex: 1, p: { xs: 2, sm: 3 }, minWidth: 0, overflowX: "auto", "&:focus": { outline: "none" } }}>
          <RouteErrorBoundary key={location.pathname}>
            <Routes>
              <Route
                index
                element={
                  homePath ? (
                    <Navigate to={homePath} replace />
                  ) : (
                    <Notice>Your account doesn't have access to any screens yet. Ask an administrator to give it a role.</Notice>
                  )
                }
              />
              {/* Every signed-in user has an inbox, so it isn't a role-gated section. */}
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="account/password" element={<ChangePasswordPage />} />
              {SECTIONS.map((s) => (
                <Route
                  key={s.path}
                  path={`${s.path}/*`}
                  element={allowed(s) ? s.element : <Notice>You don't have access to this screen.</Notice>}
                />
              ))}
              <Route path="*" element={<Notice>This page doesn't exist. Use the menu to find what you need.</Notice>} />
            </Routes>
          </RouteErrorBoundary>
        </Box>
      </Box>
    </Box>
  );
}
