import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getFund, listBanks, listFunds, proposeFund, proposeFundUpdate } from "../api/funds";
import type { FundInput } from "../api/types";

export const fundKeys = {
  all: ["funds"] as const,
  list: (q: string) => ["funds", "list", q] as const,
  detail: (id: string) => ["funds", "detail", id] as const,
};

export function useFunds(q = "") {
  return useQuery({ queryKey: fundKeys.list(q), queryFn: () => listFunds(q || undefined) });
}

export function useFund(id: string | undefined) {
  return useQuery({ queryKey: fundKeys.detail(id ?? ""), queryFn: () => getFund(id!), enabled: !!id });
}

// Reference data barely changes: keep it for the session.
export function useBanks() {
  return useQuery({ queryKey: ["reference", "banks"], queryFn: listBanks, staleTime: Infinity });
}

export function useProposeFund() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: FundInput }) => (id ? proposeFundUpdate(id, input) : proposeFund(input)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: fundKeys.all });
    },
  });
}
