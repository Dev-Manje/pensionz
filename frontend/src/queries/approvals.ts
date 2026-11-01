import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { approveRequest, cancelRequest, getApproval, listApprovals, rejectRequest } from "../api/approvals";
import type { ApprovalStatus } from "../api/types";

export const approvalKeys = {
  all: ["approvals"] as const,
  list: (status: ApprovalStatus | "all") => ["approvals", "list", status] as const,
  detail: (id: string) => ["approvals", "detail", id] as const,
};

export function useApprovals(status: ApprovalStatus | "all") {
  return useQuery({ queryKey: approvalKeys.list(status), queryFn: () => listApprovals(status) });
}

export function useApproval(id: string) {
  return useQuery({ queryKey: approvalKeys.detail(id), queryFn: () => getApproval(id) });
}

// A decision can change the record it applies to (e.g. a user), so refresh broadly.
export function useDecideApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; action: "approve" | "reject" | "cancel"; comment?: string }) =>
      args.action === "approve"
        ? approveRequest(args.id, args.comment)
        : args.action === "reject"
          ? rejectRequest(args.id, args.comment ?? "")
          : cancelRequest(args.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["funds"] });
      queryClient.invalidateQueries({ queryKey: ["schemes"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
