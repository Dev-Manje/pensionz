// Product branding in one place. Pensionz is an independent product: to theme
// it for a client (logo, name, colours), change this file and the matching
// BRAND_* settings in backend/app/core/config.py — nothing else.

export const BRAND = {
  name: "Pensionz",
  // Who runs the funds, as members and principal officers should read it.
  administrator: "your pension administrator",
  colors: {
    primary: "#0b5c6b",
    primaryDark: "#07434f",
    primaryLight: "#3a7f8c",
    background: "#f1f5f6",
    authGradientTop: "#e3eef0",
  },
} as const;
