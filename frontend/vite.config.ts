/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5178,
    // Vite only answers requests for localhost / IP addresses unless the host name is
    // listed: on a server reached by name (UAT) set VITE_ALLOWED_HOSTS=uat.example.org
    // (comma-separated) in .env.
    allowedHosts: process.env.VITE_ALLOWED_HOSTS ? process.env.VITE_ALLOWED_HOSTS.split(",").map((h) => h.trim()) : [],
    // Docker Desktop's bind mount on Windows doesn't reliably forward native
    // filesystem change events into the container, so Vite's default
    // watcher never notices edits and keeps serving stale transforms.
    // Polling works around it at the cost of a small CPU/latency overhead.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
  // Unit tests (Vitest): `npm test` (once) or `npm run test:watch`. Files next
  // to the code as *.test.ts(x). Dates are checked in Malawi time.
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    env: { TZ: "Africa/Blantyre" },
  },
});
