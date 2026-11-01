import { createTheme } from "@mui/material/styles";
import { BRAND } from "./brand";

// Colours come from brand.ts so the product can be re-themed in one place.

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: BRAND.colors.primary,
      dark: BRAND.colors.primaryDark,
      light: BRAND.colors.primaryLight,
    },
    success: { main: "#147a5f" },
    // Colours meet WCAG AA (4.5:1) for text on white and on the page background.
    warning: { main: "#8a5c14" },
    info: { main: "#0b6aa2" },
    error: { main: "#b8433a" },
    background: {
      default: BRAND.colors.background,
      paper: "#ffffff",
    },
    text: {
      primary: "#161b26",
      secondary: "#5b6572",
      // also used for real content ("—", "Nothing pending"), not only disabled controls
      disabled: "#646b77",
    },
    divider: "#dce0e6",
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    h1: { fontSize: "1.5rem", fontWeight: 600 },
    h2: { fontSize: "1.25rem", fontWeight: 600 },
    h3: { fontSize: "1.0625rem", fontWeight: 600 },
    h4: { fontSize: "0.8125rem", fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    // A clear keyboard-focus ring on everything (MUI's own is a faint ripple);
    // mouse clicks don't show it (:focus-visible). Motion is cut for people
    // who ask their system for less.
    MuiCssBaseline: {
      styleOverrides: {
        // "body" raises specificity above ButtonBase's own `outline: 0`
        "body :focus-visible": { outline: `2px solid ${BRAND.colors.primary}`, outlineOffset: 2 },
        "@media (prefers-reduced-motion: reduce)": {
          "*, *::before, *::after": { animationDuration: "0.01ms !important", transitionDuration: "0.01ms !important" },
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { border: "1px solid #dce0e6" },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: {
          fontWeight: 600,
          textTransform: "uppercase",
          fontSize: "0.6875rem",
          letterSpacing: "0.04em",
          color: "#5b6572",
          backgroundColor: "#f7f8fa",
        },
      },
    },
    // Every dialog fills the screen on a phone (< 600px): room for forms and
    // the on-screen keyboard, actions stay at the bottom.
    MuiDialog: {
      styleOverrides: {
        paper: ({ theme }) => ({
          [theme.breakpoints.down("sm")]: {
            margin: 0,
            width: "100%",
            maxWidth: "100%",
            height: "100%",
            maxHeight: "100%",
            borderRadius: 0,
            border: 0,
          },
        }),
      },
    },
    // Tab bars scroll (with arrows on phones) instead of cutting off the last
    // tabs on narrow screens. A screen can still pass its own variant.
    MuiTabs: {
      // Scrollable so long tab bars swipe on phones; no arrow buttons (they lingered after resizes).
      defaultProps: { variant: "scrollable", scrollButtons: false },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
  },
});
