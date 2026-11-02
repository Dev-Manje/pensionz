import { apiFetch } from "./client";
import type { PoDashboard, PortalScheme } from "./types";

// Principal officer portal (/po). The server returns only the employers the
// signed-in officer is linked to — possibly several, in several funds.
export function listMySchemes() {
  return apiFetch<PortalScheme[]>("/po/schemes");
}

export function getDashboard() {
  return apiFetch<PoDashboard>("/po/dashboard");
}
