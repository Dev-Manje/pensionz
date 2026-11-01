import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listFeeRules, proposeFeeRule } from "../api/feeRules";
import type { FeeRuleInput } from "../api/types";

export function useFeeRules(fundId: string) {
  return useQuery({ queryKey: ["fee-rules", fundId], queryFn: () => listFeeRules(fundId) });
}

export function useProposeFeeRule(fundId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: FeeRuleInput }) => proposeFeeRule(fundId, input, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fee-rules", fundId] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}
