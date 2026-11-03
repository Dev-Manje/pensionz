import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listOfficers, proposeOfficer, proposeOfficerUpdate, sendOfficerInvitation, type OfficerInput } from "../api/officers";

export function useOfficers(q: string) {
  return useQuery({ queryKey: ["officers", q], queryFn: () => listOfficers(q || undefined) });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["approvals"] });
    queryClient.invalidateQueries({ queryKey: ["officers"] });
  };
}

export function useProposeOfficer() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (input: OfficerInput) => proposeOfficer(input), onSuccess: invalidate });
}

export function useProposeOfficerUpdate() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: OfficerInput }) => proposeOfficerUpdate(id, input),
    onSuccess: invalidate,
  });
}

export function useSendOfficerInvitation() {
  return useMutation({ mutationFn: (id: string) => sendOfficerInvitation(id) });
}
