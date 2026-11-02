import { apiFetch } from "./client";
import type { KycApplication, Organisation, PoDashboard, PortalScheme } from "./types";

// Principal officer portal (/po). The server returns only the employers the
// signed-in officer is linked to — possibly several, in several funds.
export function listMySchemes() {
  return apiFetch<PortalScheme[]>("/po/schemes");
}

export function getDashboard() {
  return apiFetch<PoDashboard>("/po/dashboard");
}

export function getOrganisation(schemeId: string) {
  return apiFetch<Organisation>(`/po/schemes/${schemeId}/organisation`);
}

// The employer's KYC, or a change to approved details (prefilled from them).
export function startSchemeKyc(schemeId: string) {
  return apiFetch<KycApplication>(`/po/schemes/${schemeId}/kyc`, { method: "POST" });
}
