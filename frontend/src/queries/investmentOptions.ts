import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listInvestmentOptions, proposeInvestmentOption } from "../api/investmentOptions";
import type { InvestmentOptionInput } from "../api/types";

export function useInvestmentOptions(fundId: string) {
  return useQuery({ queryKey: ["investment-options", fundId], queryFn: () => listInvestmentOptions(fundId) });
}

export function useProposeInvestmentOption(fundId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: InvestmentOptionInput }) => proposeInvestmentOption(fundId, input, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investment-options", fundId] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
