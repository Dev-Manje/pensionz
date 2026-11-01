import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getScheme, listOfficerCandidates, listSchemes, proposeScheme, proposeSchemeUpdate } from "../api/schemes";
import type { SchemeInput } from "../api/types";

export const schemeKeys = {
  all: ["schemes"] as const,
  list: (fundId: string) => ["schemes", "list", fundId] as const,
  detail: (id: string) => ["schemes", "detail", id] as const,
};

export function useSchemes(fundId: string) {
  return useQuery({ queryKey: schemeKeys.list(fundId), queryFn: () => listSchemes(fundId) });
}

export function useScheme(id: string | undefined) {
  return useQuery({ queryKey: schemeKeys.detail(id ?? ""), queryFn: () => getScheme(id!), enabled: !!id });
}

export function useOfficerCandidates() {
  return useQuery({ queryKey: ["schemes", "officer-candidates"], queryFn: listOfficerCandidates });
}

export function useProposeScheme(fundId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id?: string; input: SchemeInput }) => (id ? proposeSchemeUpdate(id, input) : proposeScheme(fundId, input)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: schemeKeys.all });
    },
  });
}
