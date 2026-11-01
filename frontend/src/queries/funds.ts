import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { closePeriod, getFund, getPeriods, listBanks, listFunds, openFirstPeriod, proposeFund, proposeFundUpdate, requestReopen } from "../api/funds";
import type { FundInput } from "../api/types";

export const fundKeys = {
  all: ["funds"] as const,
  list: (q: string) => ["funds", "list", q] as const,
  detail: (id: string) => ["funds", "detail", id] as const,
  periods: (id: string) => ["funds", "periods", id] as const,
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

export function usePeriods(fundId: string) {
  return useQuery({ queryKey: fundKeys.periods(fundId), queryFn: () => getPeriods(fundId) });
}

type PeriodAction =
  | { action: "open" | "close"; period: string }
  | { action: "reopen"; periodId: string; reason: string };

// Opening/closing changes the fund's current month too, so refresh all fund queries.
export function usePeriodAction(fundId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: PeriodAction): Promise<unknown> => {
      switch (args.action) {
        case "open":
          return openFirstPeriod(fundId, args.period);
        case "close":
          return closePeriod(fundId, args.period);
        case "reopen":
          return requestReopen(fundId, args.periodId, args.reason);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: fundKeys.all });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
