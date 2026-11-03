import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getContributionsTrail, getEnquiry, getMyBeneficiaries, getMyContributions, getMyMember, getMyRequests, getMyTransactions, getStatement,
  getTrail, invitePortal, listMemberships, listMyKyc, proposeMyNomination, publishStatements, requestBankChange, requestContactChange,
  sendBankCode, startMyKyc,
} from "../api/enquiries";
import type { BeneficiaryInput } from "../api/types";

// ---- staff

export const useEnquiry = (id: string | undefined) => useQuery({ queryKey: ["enquiry", id], queryFn: () => getEnquiry(id!), enabled: !!id });
export const useStatement = (id: string, start?: string, end?: string) =>
  useQuery({ queryKey: ["enquiry", id, "statement", start, end], queryFn: () => getStatement(id, start, end), placeholderData: keepPreviousData });
export const useTrail = (id: string, start?: string, end?: string) =>
  useQuery({ queryKey: ["enquiry", id, "trail", start, end], queryFn: () => getTrail(id, start, end), placeholderData: keepPreviousData });
export const useContributionsTrail = (id: string, start?: string, end?: string) =>
  useQuery({ queryKey: ["enquiry", id, "contributions", start, end], queryFn: () => getContributionsTrail(id, start, end), placeholderData: keepPreviousData });
export const usePublishStatements = () =>
  useMutation({ mutationFn: ({ fundId, asAt, schemeId }: { fundId: string; asAt: string; schemeId?: string }) => publishStatements(fundId, asAt, schemeId) });
export function useInvitePortal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => invitePortal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["enquiry"] });
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
  });
}

// ---- member portal

export const myKeys = { all: ["my"] as const };
export const useMemberships = () => useQuery({ queryKey: ["my", "members"], queryFn: listMemberships });
export const useMyMember = (id: string | undefined) => useQuery({ queryKey: ["my", "member", id], queryFn: () => getMyMember(id!), enabled: !!id });
export const useMyTransactions = (id: string, page: number) =>
  useQuery({ queryKey: ["my", "transactions", id, page], queryFn: () => getMyTransactions(id, page), placeholderData: keepPreviousData });
export const useMyContributions = (id: string, start?: string, end?: string) =>
  useQuery({ queryKey: ["my", "contributions", id, start, end], queryFn: () => getMyContributions(id, start, end), placeholderData: keepPreviousData });
export const useMyBeneficiaries = (id: string) => useQuery({ queryKey: ["my", "beneficiaries", id], queryFn: () => getMyBeneficiaries(id) });
export const useMyRequests = (id: string) => useQuery({ queryKey: ["my", "requests", id], queryFn: () => getMyRequests(id) });
export const useMyKyc = () => useQuery({ queryKey: ["my", "kyc"], queryFn: listMyKyc });

function useMyMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => queryClient.invalidateQueries({ queryKey: myKeys.all }) });
}

export const useMyNomination = (id: string) =>
  useMyMutation((body: { signed_date: string; note: string | null; beneficiaries: BeneficiaryInput[] }) => proposeMyNomination(id, body));
export const useContactChange = (id: string) => useMyMutation((body: Record<string, string | null>) => requestContactChange(id, body));
export const useBankCode = (id: string) => useMutation({ mutationFn: () => sendBankCode(id) });
export const useBankChange = (id: string) =>
  useMyMutation((body: { bank_id: string; bank_branch_id: string | null; bank_account_name: string; bank_account_number: string; code: string }) =>
    requestBankChange(id, body),
  );
export const useStartMyKyc = (id: string) => useMyMutation(() => startMyKyc(id));
