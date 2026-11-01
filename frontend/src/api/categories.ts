import { apiFetch } from "./client";
import type { Approval, BenefitCategory, CategoryStatus, CategoryTermsInput } from "./types";

export function listCategories(schemeId: string) {
  return apiFetch<BenefitCategory[]>(`/schemes/${schemeId}/categories`);
}

export function getCategory(id: string) {
  return apiFetch<BenefitCategory>(`/categories/${id}`);
}

// Both return the approval request: a scheme-setup checker must approve it.
export function proposeCategory(schemeId: string, input: { code: string; name: string; terms: CategoryTermsInput }) {
  return apiFetch<Approval>(`/schemes/${schemeId}/categories`, { method: "POST", body: JSON.stringify(input) });
}

export function proposeCategoryChange(id: string, input: { name: string; status: CategoryStatus; terms: CategoryTermsInput | null }) {
  return apiFetch<Approval>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(input) });
}
