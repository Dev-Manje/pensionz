/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5178,
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
