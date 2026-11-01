import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDeclaration, getKyc, kycOptions, listKyc } from "../api/kyc";
import type { ClientType, KycApplication, KycStatus } from "../api/types";

export const kycKeys = {
  all: ["kyc"] as const,
  list: (status: KycStatus | null, q: string) => ["kyc", "list", status, q] as const,
  detail: (id: string) => ["kyc", "detail", id] as const,
};

export function useKycList(status: KycStatus | null, q: string) {
  return useQuery({ queryKey: kycKeys.list(status, q), queryFn: () => listKyc(status, q || undefined) });
}

export function useKyc(id: string | undefined) {
  return useQuery({ queryKey: kycKeys.detail(id ?? ""), queryFn: () => getKyc(id!), enabled: !!id });
}

export function useKycOptions() {
  return useQuery({ queryKey: ["kyc", "options"], queryFn: kycOptions, staleTime: Infinity });
}

export function useDeclaration(type: ClientType) {
  return useQuery({ queryKey: ["kyc", "declaration", type], queryFn: () => getDeclaration(type) });
}

// Every KYC action returns the updated application: keep it and refresh the lists.
export function useKycAction<A>(fn: (args: A) => Promise<KycApplication>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (app) => {
      queryClient.setQueryData(kycKeys.detail(app.id), app);
      queryClient.invalidateQueries({ queryKey: ["kyc", "list"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
