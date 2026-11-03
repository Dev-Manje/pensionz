import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createRun, discardRun, getRun, listDeclarations, proposeDeclaration, recalculateRun, reverseRun, submitRun, type DeclarationInput,
} from "../api/bonus";

export const bonusKeys = {
  all: ["bonus"] as const,
  declarations: (fundId: string) => ["bonus", "declarations", fundId] as const,
  run: (id: string) => ["bonus", "run", id] as const,
};

export const useDeclarations = (fundId: string) => useQuery({ queryKey: bonusKeys.declarations(fundId), queryFn: () => listDeclarations(fundId) });
export const useBonusRun = (id: string | undefined) => useQuery({ queryKey: bonusKeys.run(id ?? ""), queryFn: () => getRun(id!), enabled: !!id });

function useBonusMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bonusKeys.all });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

export const useProposeDeclaration = (fundId: string) => useBonusMutation((input: DeclarationInput) => proposeDeclaration(fundId, input));
export const useCreateRun = () =>
  useBonusMutation(({ declarationId, body }: { declarationId: string; body: { member_ids?: string[]; as_at?: string | null; posting_date?: string | null } }) =>
    createRun(declarationId, body),
  );
export const useRecalculateRun = () => useBonusMutation((id: string) => recalculateRun(id));
export const useDiscardRun = () => useBonusMutation((id: string) => discardRun(id));
export const useSubmitRun = () => useBonusMutation((id: string) => submitRun(id));
export const useReverseRun = () => useBonusMutation(({ id, reason, member_ids }: { id: string; reason: string; member_ids?: string[] }) => reverseRun(id, { reason, member_ids }));
