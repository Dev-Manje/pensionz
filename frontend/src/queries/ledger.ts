import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getFundChart, getMemberLedger, listJournal } from "../api/ledger";

export const ledgerKeys = {
  all: ["ledger"] as const,
  chart: (fundId: string) => ["ledger", "chart", fundId] as const,
  journal: (fundId: string, account: string, page: number, pageSize: number) => ["ledger", "journal", fundId, account, page, pageSize] as const,
  member: (memberId: string, page: number, pageSize: number) => ["ledger", "member", memberId, page, pageSize] as const,
};

export function useFundChart(fundId: string) {
  return useQuery({ queryKey: ledgerKeys.chart(fundId), queryFn: () => getFundChart(fundId) });
}

export function useJournal(fundId: string, account: string, page: number, pageSize: number) {
  return useQuery({
    queryKey: ledgerKeys.journal(fundId, account, page, pageSize),
    queryFn: () => listJournal(fundId, { account: account || undefined, page: page + 1, pageSize }),
    placeholderData: keepPreviousData,
  });
}

export function useMemberLedger(memberId: string, page: number, pageSize: number) {
  return useQuery({
    queryKey: ledgerKeys.member(memberId, page, pageSize),
    queryFn: () => getMemberLedger(memberId, page + 1, pageSize),
    placeholderData: keepPreviousData,
  });
}
