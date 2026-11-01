import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { calculateTax, getTaxTables, listParameters, proposeParameter, proposeTaxTable } from "../api/regulatory";
import type { TaxTableKind } from "../api/types";

export function useParameters() {
  return useQuery({ queryKey: ["regulatory", "parameters"], queryFn: listParameters });
}

export function useTaxTables(kind: TaxTableKind) {
  return useQuery({ queryKey: ["regulatory", "tax", kind], queryFn: () => getTaxTables(kind) });
}

export function useTaxCalc(kind: TaxTableKind, amount: string) {
  return useQuery({
    queryKey: ["regulatory", "tax", kind, "calc", amount],
    queryFn: () => calculateTax(kind, amount),
    enabled: amount !== "" && Number(amount) >= 0,
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["regulatory"] });
    queryClient.invalidateQueries({ queryKey: ["approvals"] });
  };
}

export function useProposeParameter() {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: ({ key, ...input }: { key: string; value: string; effective_from: string; source: string | null }) => proposeParameter(key, input),
    onSuccess,
  });
}

export function useProposeTaxTable(kind: TaxTableKind) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: (input: { effective_from: string; source: string | null; bands: { lower: string; rate_pct: string }[] }) => proposeTaxTable(kind, input),
    onSuccess,
  });
}
