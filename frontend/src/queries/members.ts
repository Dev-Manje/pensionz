import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { findDuplicates, getEmployment, getMember, getNominations, kycPrefill, listMembers, listParties, type MemberFilters } from "../api/members";

export const memberKeys = {
  all: ["members"] as const,
  list: (filters: MemberFilters) => ["members", "list", filters] as const,
  detail: (id: string) => ["members", "detail", id] as const,
};

export function useMembers(filters: MemberFilters) {
  return useQuery({ queryKey: memberKeys.list(filters), queryFn: () => listMembers(filters), placeholderData: keepPreviousData });
}

export function useMember(id: string | undefined) {
  return useQuery({ queryKey: memberKeys.detail(id ?? ""), queryFn: () => getMember(id!), enabled: !!id });
}

export function useDuplicates(params: Parameters<typeof findDuplicates>[0], enabled: boolean) {
  return useQuery({ queryKey: ["members", "duplicates", params], queryFn: () => findDuplicates(params), enabled });
}

export function useParties(clientType: "individual" | "corporate", enabled = true) {
  return useQuery({ queryKey: ["kyc", "parties", clientType], queryFn: () => listParties(clientType), enabled });
}

export function useKycPrefill() {
  return useMutation({ mutationFn: kycPrefill });
}

// Every member proposal returns an approval request: refresh approvals and members.
export function useMemberProposal<A>(fn: (args: A) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: memberKeys.all });
    },
  });
}

export function useNominations(memberId: string) {
  return useQuery({ queryKey: ["members", "beneficiaries", memberId], queryFn: () => getNominations(memberId) });
}

export function useEmployment(memberId: string) {
  return useQuery({ queryKey: ["members", "employment", memberId], queryFn: () => getEmployment(memberId) });
}
