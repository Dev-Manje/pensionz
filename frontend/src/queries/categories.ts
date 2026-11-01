import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getCategory, listCategories, proposeCategory, proposeCategoryChange } from "../api/categories";
import type { CategoryStatus, CategoryTermsInput } from "../api/types";

export function useCategories(schemeId: string) {
  return useQuery({ queryKey: ["categories", "list", schemeId], queryFn: () => listCategories(schemeId) });
}

export function useCategory(id: string | undefined) {
  return useQuery({ queryKey: ["categories", "detail", id ?? ""], queryFn: () => getCategory(id!), enabled: !!id });
}

type Proposal =
  | { schemeId: string; code: string; name: string; terms: CategoryTermsInput }
  | { categoryId: string; name: string; status: CategoryStatus; terms: CategoryTermsInput | null };

export function useProposeCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (p: Proposal) =>
      "categoryId" in p
        ? proposeCategoryChange(p.categoryId, { name: p.name, status: p.status, terms: p.terms })
        : proposeCategory(p.schemeId, { code: p.code, name: p.name, terms: p.terms }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
